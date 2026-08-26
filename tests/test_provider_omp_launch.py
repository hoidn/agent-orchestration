"""Pinned OMP launch adapter contracts (Task 5, OMP-I1).

Exercises ``omp_launch.run(..., pin=fake_pin, binary_resolver=fake_resolver)``
directly with the fake OMP child and the real kernel Landlock path.
"""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import re
import secrets
import socket
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

import orchestrator.providers.omp_launch as omp_launch
from orchestrator.providers import omp_launch_contract
from orchestrator.providers import omp_launch_policy
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_transport import OmpJsonStdoutAccumulator
from orchestrator.providers.omp_write_confinement import (
    canonical_policy_digest,
    main as helper_main,
)
from orchestrator.providers.types import OmpTransportExpectation

FAKE_VERSION = "17.3.4"
MODEL = "openai-codex/gpt-5.6-sol"
TS = "2026-08-23T22:33:14.831Z"
TS_STEM = "2026-08-23T22-33-14-831Z"
SESSION_ID = "sess-xyz"
VISIT_KEY = "step-1__v2"

_BROKER_URL_RE = re.compile(r"^http://127\.0\.0\.1:\d+$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_POSITIVE_ENV_NAMES = frozenset(
    {
        "HOME", "PATH", "LANG", "LC_ALL", "TMPDIR",
        "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME",
        "PI_CODING_AGENT_DIR", "OMP_BROKER_URL", "OMP_BROKER_TOKEN",
    }
)

# Task 10 R2 closed profile schema: adapter-owned attempt roots + broker pair.
_PROFILE_ENV_NAMES = frozenset(omp_launch_contract.PROFILE_ENV_NAMES)

_FAKE_SOURCE = Path(__file__).parent / "fixtures" / "omp" / "fake_omp.py"
_FAKE_SOURCE_ABS = str(_FAKE_SOURCE.resolve())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _fake_pin() -> OmpBinaryPin:
    return dataclasses.replace(
        OMP_BINARY_PIN,
        version=FAKE_VERSION,
        executable_sha256=_sha256_file(_FAKE_SOURCE),
    )


def _compile_launcher(script: Path) -> Path:
    """Compile the native fake launcher for one script (once per session).

    The confined helper and the ambient fd-exec route exec the verified
    private copy through a descriptor (execveat with AT_EMPTY_PATH), which
    the kernel refuses for shebang scripts. The production pinned binary is a
    native ELF, so the fixture needs a native launcher that hands control to
    the python fake with the script path embedded at compile time.
    """
    src = Path(__file__).parent / "fixtures" / "omp" / "fake_launcher.c"
    cache = Path(os.getcwd()) / ".tmp" / "omp-fake-launcher"
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(str(script.resolve()).encode("utf-8")).hexdigest()[:10]
    launcher = cache / f"fake_launcher_{tag}"
    if not launcher.exists():
        subprocess.run(
            ["cc", "-O1", "-o", str(launcher), str(src),
             f'-DOMP_FAKE_SCRIPT="{script}"'],
            check=True,
            capture_output=True,
            env={**os.environ, "TMPDIR": str(cache)},  # /tmp can be full
        )
    launcher.chmod(0o500)
    return launcher


def _fake_launcher() -> Path:
    return _compile_launcher(_FAKE_SOURCE)


def _launcher_pin() -> OmpBinaryPin:
    return dataclasses.replace(
        _fake_pin(), executable_sha256=_sha256_file(_fake_launcher())
    )


def _make_home(root: Path) -> Path:
    agents = root / "home" / ".omp" / "agent" / "agents"
    agents.mkdir(parents=True)
    (agents / "custom.md").write_text(
        "---\nname: custom\ndescription: test agent\n---\nbody\n", encoding="utf-8"
    )
    home = root / "home"
    home.chmod(0o700)  # a real private home; the machine umask is not 0o022
    return home


def _private_fixture(root: Path, digest: str, payload: bytes) -> Path:
    private = root / digest / f"attempt-{'0' * 32}" / "omp"
    private.parent.mkdir(parents=True)
    private.parent.chmod(0o700)
    private.write_bytes(payload)
    private.chmod(0o500)
    return private


def _make_conf(root: Path) -> Path:
    conf = root / "conf"
    conf.mkdir()
    (conf / "config.yml").write_text(
        "advisor:\n  enabled: false\n"
        "memory:\n  backend: \"off\"\n"
        "task:\n  maxConcurrency: 2\n  maxRecursionDepth: 0\n"
        "  disabledAgents: [designer, librarian, reviewer, scout, security-reviewer, sonic, task]\n",
        encoding="utf-8",
    )
    return conf


def _live_dir(root: Path, key: str = VISIT_KEY) -> Path:
    """Private OMP fresh session dir (the machine umask is 0o002)."""
    session_dir = root / "visits" / key
    session_dir.mkdir(parents=True)
    session_dir.chmod(0o700)
    return session_dir


def _std_env(home: Path, root: Path) -> dict[str, str]:
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(root / "tmp"),
        "XDG_CACHE_HOME": str(root / "cache"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_STATE_HOME": str(root / "state"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "SECRET_CANARY": "must-not-leak",
        "CALLER_CANARY": "caller-only",
    }
    for path in (env["TMPDIR"], env["XDG_CACHE_HOME"], env["XDG_DATA_HOME"],
                 env["XDG_STATE_HOME"], env["XDG_CONFIG_HOME"]):
        Path(path).mkdir(parents=True, exist_ok=True)
    return env


def _env_roots(env: dict[str, str]) -> dict[str, str]:
    return {role: env[f"XDG_{role.upper()}_HOME"] for role in ("data", "state", "cache")} | {
        "temp": env["TMPDIR"]
    }


def _control(**overrides) -> bytes:
    payload = {"fake": 1, "id": SESSION_ID, "ts": TS, "reply": "OK"}
    payload.update(overrides)
    return json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"


def _adapter_argv(lane: str, **extra) -> list[str]:
    argv = ["run", "--lane", lane, "--model", MODEL]
    for flag, value in extra.items():
        if flag == "conf_root":
            argv += ["--conf-root", value]
        elif flag == "session_dir":
            argv += ["--provider-session-dir", value]
        else:  # pragma: no cover
            raise AssertionError(f"unexpected adapter arg {flag!r}")
    return argv


def _run(*, argv, env, workspace, stdin, pin, out, err, resolver_path=_FAKE_SOURCE,
         resolver=None) -> int:
    previous = os.getcwd()
    os.chdir(workspace)
    try:
        if resolver is None:
            resolver = (
                lambda: resolver_path
                if os.path.isabs(str(resolver_path))
                else str(Path(resolver_path).resolve())
            )
        return omp_launch.run(
            argv=argv, env=env, stdin=stdin, out=out, err=err,
            pin=pin, binary_resolver=resolver,
        )
    finally:
        os.chdir(previous)


def _reports(err_text: str) -> dict[str, list[str]]:
    reports: dict[str, list[str]] = {}
    for line in err_text.splitlines():
        label, _, value = line.partition(" ")
        if label.startswith("FAKE_"):
            reports.setdefault(label[len("FAKE_"):], []).append(value)
    return reports


def _frame_bytes(out: bytes) -> tuple[bytes, dict]:
    lines = out.split(b"\n")
    assert len(lines) >= 2 and lines[-1] == b"", "stream must end with a frame line"
    return b"\n".join(lines[:-2]) + b"\n", json.loads(lines[-2])


def _accumulate(out: bytes, expectation: OmpTransportExpectation):
    accumulator = OmpJsonStdoutAccumulator(expectation=expectation)
    accumulator.feed(out)
    return accumulator.finalize(expected_session_id=SESSION_ID, require_terminal=True)


def _assert_success(*, rc, out, err, expectation) -> dict:
    assert rc == 0, err.getvalue()
    child_bytes, frame = _frame_bytes(out.getvalue())
    assert json.dumps(frame, separators=(",", ":")) in out.getvalue().decode("utf-8")
    metadata, error = _accumulate(out.getvalue(), expectation)
    assert error is None, error
    assert metadata is not None
    return frame


def _expectation(pin, argv, *, lane="ambient", persistence="none", session_dir=None,
                 conf_root=None, env=None, visit_key=None, observed=(), nonce=None,
                 **extra) -> OmpTransportExpectation:
    kwargs = dict(
        lane=lane,
        persistence=persistence,
        binary=omp_launch.binary_projection(pin),
        stdout_session_id=SESSION_ID,
        child_argv=tuple(argv),
        observed_relpaths=observed,
    )
    if visit_key is not None:
        kwargs["visit_key"] = visit_key
    if lane in ("no-tools", "conf", "conf-inference"):
        if conf_root is None:
            conf_root = str(omp_launch.neutral_conf_root())
        kwargs["conf_manifest_sha256"] = admit_conf_tree(
            os.open(conf_root, os.O_RDONLY)
        ).manifest_sha256
        attempt = omp_launch_policy.profile_attempt_roots(
            env_roots=_env_roots(env), lane=lane, workspace=str(workspace_path),
            session_dir=session_dir, conf_root=conf_root, nonce=nonce,
        )
        empty_cwd = omp_launch.empty_omp_cwd(
            home=env["HOME"], lane=lane, workspace=str(workspace_path),
            session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
            nonce=nonce,
        )
        kwargs["confinement_policy_sha256"] = canonical_policy_digest(
            lane=lane, home_omp=os.path.join(attempt["HOME"], ".omp"),
            session_dir=session_dir, conf_root=conf_root,
            workspace=str(workspace_path), empty_cwd=empty_cwd,
            env_roots=omp_launch_policy.attempt_env_roots(attempt),
        )
    kwargs.update(extra)
    return OmpTransportExpectation(**kwargs)


def _frozen_profile_expectation(pin, argv, *, lane, env, conf_root=None,
                                session_dir=None, visit_key=None,
                                persistence="none", observed=()):
    """Freeze the profile expectation before the run, like the parent does.

    Production freezes the expectation (and the empty-cwd directory identity)
    at prepare time, then carries the prepared empty cwd to the adapter via
    the code-owned internal carrier; the adapter opens it (never adopts a
    pre-existing predictable dir) and removes it at run end. The helper
    therefore returns ``(expectation, run_env)`` with the carrier injected so
    the adapter's digest matches the frozen one exactly.
    """
    from orchestrator.providers.omp_launch_policy import (
        ATTEMPT_FDS_ENV,
        EMPTY_CWD_ENV,
        create_profile_attempt_authority,
        profile_attempt_roots,
    )

    if conf_root is None and lane in ("no-tools", "conf", "conf-inference"):
        conf_root = str(omp_launch.neutral_conf_root())
    nonce = secrets.token_hex(8)
    empty_cwd = omp_launch.empty_omp_cwd(
        home=env["HOME"], lane=lane, workspace=str(workspace_path),
        session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
        nonce=nonce,
    )
    omp_launch.create_empty_omp_cwd(empty_cwd)
    attempt = profile_attempt_roots(
        env_roots=_env_roots(env),
        lane=lane,
        workspace=str(workspace_path),
        session_dir=session_dir,
        conf_root=conf_root,
        nonce=nonce,
    )
    authority = create_profile_attempt_authority(attempt)
    run_env = {
        **env,
        EMPTY_CWD_ENV: str(empty_cwd),
        ATTEMPT_FDS_ENV: authority.carrier(),
    }
    return _expectation(
        pin, argv, lane=lane, persistence=persistence, session_dir=session_dir,
        conf_root=conf_root, env=env, visit_key=visit_key, observed=observed,
        nonce=nonce,
    ), run_env


#: populated by the fixture below; keeps expectation builders compact
workspace_path: Path = Path(".")


@pytest.fixture(autouse=True)
def _set_workspace_path(tmp_path):
    global workspace_path
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parser_contract(tmp_path) -> None:
    env = _std_env(_make_home(tmp_path), tmp_path)

    def _fails(argv: list[str], needle: str) -> None:
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=argv, env=env, workspace=workspace_path,
                  stdin=_control(), pin=_fake_pin(), out=out, err=err)
        assert rc == 2, (rc, err.getvalue())
        assert needle in err.getvalue(), err.getvalue()
        assert out.getvalue() == b"", "no child output on parser failure"

    _fails(["run", "--lane", "omp", "--model", MODEL, "prompt.txt"], "positional")
    _fails(["run", "--lane", "omp", "--model", MODEL, "--bogus"], "unexpected")
    _fails(["run", "--lane", "omp"], "model")
    _fails(["run", "--model", MODEL], "lane")
    _fails(["run", "--lane", "not-a-lane", "--model", MODEL], "lane")
    _fails(["run", "--lane", "omp", "--model", "a b"], "model")
    _fails(_adapter_argv("omp") + ["--lane", "omp_no_tools"], "duplicate")
    _fails(_adapter_argv("omp") + ["--model", MODEL], "duplicate")
    _fails(_adapter_argv("omp", conf_root=str(tmp_path / "conf")), "conf-root is accepted")
    _fails(["run", "--lane", "omp_conf", "--model", MODEL], "conf-root")


def test_no_tools_frozen_conf_rejects_swap_between_executor_and_adapter(
    tmp_path: Path,
) -> None:
    import shutil
    from orchestrator.providers.omp_conf import admit_conf_tree

    home = _make_home(tmp_path)
    conf = tmp_path / "conf"
    shutil.copytree(omp_launch.neutral_conf_root(), conf)
    descriptor = os.open(conf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        kind = os.fstat(descriptor)
        digest = admit_conf_tree(descriptor).manifest_sha256
    finally:
        os.close(descriptor)
    original_identity = (kind.st_dev, kind.st_ino)
    conf.rename(tmp_path / "old-conf")
    shutil.copytree(omp_launch.neutral_conf_root(), conf)
    argv = _adapter_argv("omp_no_tools", conf_root=str(conf)) + [
        "--conf-root-device", str(original_identity[0]),
        "--conf-root-inode", str(original_identity[1]),
        "--conf-manifest-sha256", digest,
    ]
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv,
        env=_broker_env(home, tmp_path),
        workspace=workspace_path,
        stdin=_control(),
        pin=_fake_pin(),
        out=out,
        err=err,
    )
    assert rc == 2
    assert "conf root identity" in err.getvalue()
    assert out.getvalue() == b""


# ---------------------------------------------------------------------------
# Ambient lanes
# ---------------------------------------------------------------------------


def test_ambient_transient_exact_argv_stream_env_and_frame(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env["PI_CODING_AGENT_DIR"] = str(home / ".omp" / "agent")
    env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] = "state/run-root/result.json"
    pin = _launcher_pin()
    argv = _adapter_argv("omp")
    stdin = _control()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=stdin, pin=pin,
              out=out, err=err, resolver_path=_fake_launcher())

    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == [
        "-p", "--mode", "json", "--no-title", "--model", MODEL,
        "--approval-mode", "write", "--no-session",
    ]
    assert reports["CWD"][0] == str(workspace_path)
    assert reports["STDIN"][0] == base64.b64encode(stdin).decode("ascii")
    # Ambient children inherit the parent environment except runtime-owned
    # bundle authority, which stays in the orchestrator parent.
    expected_env = set(env) - {"ORCHESTRATOR_OUTPUT_BUNDLE_PATH"}
    assert set(json.loads(reports["ENV"][0])) == expected_env
    assert json.loads(reports["AGENTS"][0]) == ["custom.md"]
    broker = json.loads(reports["BROKER"][0])
    assert broker["url"] is None and broker["token"] is None, (
        "ambient lanes carry no fabricated broker credential"
    )
    assert broker["agent_dir"] == str(home / ".omp" / "agent")

    frame = _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, env=env),
    )
    assert frame["type"] == "orchestrator.omp_launch.v1"
    assert frame["lane"] == "ambient"
    assert frame["persistence"] == "none"
    assert frame["child"] == {
        "argv": argv, "cwd": str(workspace_path),
        "env_names": sorted(expected_env), "exit_code": 0,
    }
    assert frame["session"] == {"id": SESSION_ID, "visit_key": None,
                                "primary_relpath": None, "primary_sha256": None}
    assert frame["conf"] == {"manifest_sha256": None}
    assert frame["confinement"] is None
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}

    # Ambient probe is unconfined: the marker write succeeds.
    assert (home / ".omp" / "version-probe-marker").read_text(encoding="utf-8") == "probe-unconfined"

    # Fresh private attempt copy, owner-exec, whole-file hash.
    private = list(
        (
            Path(env["XDG_CACHE_HOME"])
            / "omp-i1"
            / "private"
            / pin.executable_sha256
        ).glob("attempt-*/omp")
    )
    assert len(private) == 1
    assert (private[0].stat().st_mode & 0o777) == 0o500
    assert _sha256_file(private[0]) == pin.executable_sha256
    for values in reports.values():
        for value in values:
            assert _FAKE_SOURCE_ABS not in value

    # Child bytes equal a direct fake run (sole final adapter frame appended).
    import subprocess

    direct = subprocess.run(
        [sys.executable, str(_FAKE_SOURCE), "--no-session", "--mode=json", "--model", MODEL],
        input=stdin, cwd=str(workspace_path), stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, check=False,
    ).stdout
    child_bytes, _ = _frame_bytes(out.getvalue())
    assert child_bytes == direct


def test_ambient_missing_cache_root_fails_as_launch_error(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    del env["XDG_CACHE_HOME"]
    out, err = io.BytesIO(), io.StringIO()

    rc = _run(
        argv=_adapter_argv("omp"),
        env=env,
        workspace=workspace_path,
        stdin=_control(),
        pin=_launcher_pin(),
        out=out,
        err=err,
        resolver_path=_fake_launcher(),
    )

    assert rc == 2
    assert "ambient launch requires XDG_CACHE_HOME" in err.getvalue()


def test_ambient_unrestricted_yolo_and_fresh_handoff(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_unrestricted_workspace"), env=env,
              workspace=workspace_path, stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == [
        "-p", "--mode", "json", "--no-title", "--model", MODEL, "--yolo",
        "--no-session",
    ]
    _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, _adapter_argv("omp_unrestricted_workspace"),
                                 lane="ambient-unrestricted", env=env),
    )

    session_dir = _live_dir(tmp_path)
    argv = _adapter_argv("omp", session_dir=str(session_dir))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(), pin=pin,
              out=out, err=err, resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    child_args = json.loads(reports["ARGS"][0])
    assert child_args[:-1] == [
        "-p", "--mode", "json", "--no-title", "--model", MODEL,
        "--approval-mode", "write", "--session-dir",
    ]
    assert re.fullmatch(r"/proc/self/fd/[0-9]+", child_args[-1])
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    assert journal.is_file()
    frame = _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, env=env, persistence="fresh",
                                 session_dir=str(session_dir), visit_key=VISIT_KEY,
                                                                  observed=()),
    )
    assert frame["session"] == {
        "id": SESSION_ID, "visit_key": VISIT_KEY,
        "primary_relpath": journal.name, "primary_sha256": _sha256_file(journal),
    }
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}


def test_fresh_child_writes_through_retained_session_fd_after_path_swap(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    moved = session_dir.with_name("retained")
    ready = tmp_path / "child-ready"
    argv = _adapter_argv("omp", session_dir=str(session_dir))
    out, err = io.BytesIO(), io.StringIO()
    result: dict[str, int] = {}

    def launch() -> None:
        result["rc"] = _run(
            argv=argv,
            env=env,
            workspace=workspace_path,
            stdin=_control(pre_write_sleep=1, pre_write_ready_file=str(ready)),
            pin=pin,
            out=out,
            err=err,
            resolver_path=_fake_launcher(),
        )

    thread = threading.Thread(target=launch)
    thread.start()
    for _ in range(1000):
        if ready.exists():
            break
        time.sleep(0.01)
    assert ready.exists(), err.getvalue()
    session_dir.rename(moved)
    session_dir.mkdir(mode=0o700)
    thread.join(timeout=30)
    assert result.get("rc") == 0, err.getvalue()
    assert list(session_dir.iterdir()) == []
    assert [path.name for path in moved.glob("*.jsonl")] == [
        f"{TS_STEM}_{SESSION_ID}.jsonl"
    ]


# ---------------------------------------------------------------------------
# Profile lanes
# ---------------------------------------------------------------------------


def _profile_assertions(reports, env, home, lane, *, empty_cwd=None,
                        session_dir=None, workspace_add=False, conf_root=None):
    if conf_root is None and lane in ("no-tools", "conf-inference"):
        conf_root = omp_launch.neutral_conf_root()
    attempt_key = omp_launch_policy.profile_attempt_key(
        lane=lane, workspace=str(workspace_path),
        session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
    )
    if empty_cwd is None:
        nonce = None
        empty_cwd = omp_launch.empty_omp_cwd(
            home=env["HOME"], lane=lane, workspace=str(workspace_path),
            session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
        )
    else:
        nonce = omp_launch_policy.empty_omp_cwd_nonce(empty_cwd, expected_key=attempt_key)
    attempt = omp_launch_policy.profile_attempt_roots(
        env_roots=_env_roots(env), lane=lane, workspace=str(workspace_path),
        session_dir=session_dir, conf_root=conf_root, nonce=nonce,
    )
    assert reports["CWD"][0] == empty_cwd
    # The adapter removes the exclusive empty cwd and the attempt tree at run
    # end (the confined child holds the cwd read-only, so the rmdir is
    # deterministic).
    assert not os.path.exists(empty_cwd)
    assert not os.path.exists(os.path.dirname(attempt["HOME"])), "attempt tree removed"
    child_env = json.loads(reports["ENV"][0])
    assert set(child_env) <= _PROFILE_ENV_NAMES, set(child_env) - _PROFILE_ENV_NAMES
    required = {"HOME", "PATH", "SHELL", "PI_CODING_AGENT_DIR", "TMPDIR",
                "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                "XDG_CONFIG_HOME", "OMP_AUTH_BROKER_URL", "OMP_AUTH_BROKER_TOKEN"}
    assert required <= set(child_env)
    values = json.loads(reports["VALUES"][0])
    assert values["HOME"] == attempt["HOME"]
    assert values["PI_CODING_AGENT_DIR"] == os.path.join(attempt["HOME"], ".omp", "agent")
    assert values["XDG_CACHE_HOME"] == attempt["XDG_CACHE_HOME"]
    assert values["TMPDIR"] == attempt["TMPDIR"]
    assert values["OMP_AUTH_BROKER_TOKEN"] == "[redacted]"
    for secret in ("SECRET_CANARY", "CALLER_CANARY", "caller-token"):
        assert secret not in reports["ENV"][0] + reports["BROKER"][0]
    assert not (home / ".omp" / "version-probe-marker").exists()

    denied = [v for v in reports["PROBE"] if v.startswith(attempt["HOME"] + "/.omp ")]
    assert sorted(denied) == sorted(
        f"{attempt['HOME']}/.omp {op}=denied"
        for op in ("create", "write", "truncate", "replace", "rename", "restore")
    )
    spawned = [v for v in reports["SPAWNED_PROBE"] if v.startswith(attempt["HOME"] + "/.omp ")]
    assert sorted(spawned) == sorted(
        f"{attempt['HOME']}/.omp {op}=denied"
        for op in ("create", "write", "truncate", "replace", "rename", "restore")
    )
    write_roots = [attempt["XDG_DATA_HOME"], attempt["XDG_STATE_HOME"],
                   attempt["XDG_CACHE_HOME"], attempt["TMPDIR"]]
    if session_dir is not None:
        args = json.loads(reports["ARGS"][0])
        write_roots.append(args[args.index("--session-dir") + 1])
    if workspace_add:
        write_roots.append(str(workspace_path))
    for root in write_roots:
        assert sorted(v for v in reports["PROBE"] if v.startswith(root + " ")) == sorted(
            f"{root} {op}=ok" for op in ("create", "write")
        ), root
    return empty_cwd


def test_profile_no_tools_confined_probe_and_child(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    argv = _adapter_argv("omp_no_tools")
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env,
        conf_root=str(omp_launch.neutral_conf_root()),
    )

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    empty_cwd = run_env[omp_launch_policy.EMPTY_CWD_ENV]
    assert json.loads(reports["ARGS"][0]) == [
        "-p", "--mode", "json", "--no-title", "--no-extensions", "--no-skills",
        "--no-rules", "--no-tools", "--model", MODEL, "--approval-mode", "write",
        "--cwd", empty_cwd, "--no-session",
    ]
    empty_cwd = _profile_assertions(reports, env, home, "no-tools", empty_cwd=empty_cwd)

    frame = _assert_success(rc=rc, out=out, err=err, expectation=expectation)
    assert frame["child"]["cwd"] == empty_cwd
    assert frame["confinement"] == {
        "schema_version": "omp_write_confinement.v1",
        "landlock_abi": omp_launch.landlock_abi(),
        "policy_sha256": expectation.confinement_policy_sha256,
    }
    assert frame["conf"] == {"manifest_sha256": expectation.conf_manifest_sha256}


def test_profile_conf_lane_add_dir(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    conf_root = _make_conf(tmp_path)
    pin = _launcher_pin()
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="conf", env=env, conf_root=str(conf_root),
    )

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    empty_cwd = run_env[omp_launch_policy.EMPTY_CWD_ENV]
    assert json.loads(reports["ARGS"][0]) == [
        "-p", "--mode", "json", "--no-title", "--no-extensions", "--no-skills",
        "--no-rules", "--model", MODEL, "--approval-mode", "write",
        "--cwd", empty_cwd, "--add-dir", str(workspace_path), "--no-session",
    ]
    _profile_assertions(reports, env, home, "conf", empty_cwd=empty_cwd,
                        workspace_add=True, conf_root=str(conf_root))
    _assert_success(rc=rc, out=out, err=err, expectation=expectation)

def test_profile_conf_lane_uses_inherited_conf_fd_after_path_swap(
    tmp_path
) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    conf_root = _make_conf(tmp_path)
    pin = _launcher_pin()
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="conf", env=env, conf_root=str(conf_root),
    )
    conf_fd = os.open(
        conf_root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    carrier = json.loads(run_env[omp_launch_policy.ATTEMPT_FDS_ENV])
    carrier["roots"]["__conf__"] = conf_fd
    run_env[omp_launch_policy.ATTEMPT_FDS_ENV] = json.dumps(carrier)
    original = conf_root.with_name("conf-original")
    os.replace(conf_root, original)
    conf_root.mkdir()
    (conf_root / "config.yml").write_text("advisor:\n  enabled: maybe\n")

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv, env=run_env, workspace=workspace_path,
        stdin=_control(), pin=pin, out=out, err=err,
        resolver_path=_fake_launcher(),
    )

    _assert_success(rc=rc, out=out, err=err, expectation=expectation)


def test_profile_conf_inference_and_fresh_no_tools(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()

    argv = _adapter_argv("omp_conf_inference")
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="conf-inference", env=env,
        conf_root=str(omp_launch.neutral_conf_root()),
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    empty_cwd = run_env[omp_launch_policy.EMPTY_CWD_ENV]
    assert json.loads(reports["ARGS"][0]) == [
        "-p", "--mode", "json", "--no-title", "--no-extensions", "--no-skills",
        "--no-rules", "--no-tools", "--model", MODEL, "--approval-mode", "write",
        "--cwd", empty_cwd, "--no-session",
    ]
    _profile_assertions(reports, env, home, "conf-inference", empty_cwd=empty_cwd)
    _assert_success(rc=rc, out=out, err=err, expectation=expectation)

    session_dir = _live_dir(tmp_path)
    argv = _adapter_argv("omp_no_tools", session_dir=str(session_dir))
    fresh_expectation, fresh_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh",
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=fresh_env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    empty_cwd = fresh_env[omp_launch_policy.EMPTY_CWD_ENV]
    child_args = json.loads(reports["ARGS"][0])
    assert child_args[:-1] == [
        "-p", "--mode", "json", "--no-title", "--no-extensions", "--no-skills",
        "--no-rules", "--no-tools", "--model", MODEL, "--approval-mode", "write",
        "--cwd", empty_cwd, "--session-dir",
    ]
    assert re.fullmatch(r"/proc/self/fd/[0-9]+", child_args[-1])
    _profile_assertions(reports, env, home, "no-tools", empty_cwd=empty_cwd,
                        session_dir=str(session_dir))
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    assert journal.is_file()
    frame = _assert_success(rc=rc, out=out, err=err, expectation=fresh_expectation)
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}
    assert frame["session"]["primary_relpath"] == journal.name


def test_profile_conf_launches_with_prompt_snapshot_nested_under_workspace(
    tmp_path,
) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    snapshot_parent = (
        workspace_path / ".orchestrate" / "runs" / "run-1" / "prompt-inputs"
    )
    snapshot_parent.mkdir(parents=True)
    conf_root = _make_conf(snapshot_parent)
    pin = _launcher_pin()
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="conf", env=env, conf_root=str(conf_root)
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv,
        env=run_env,
        workspace=workspace_path,
        stdin=_control(),
        pin=pin,
        out=out,
        err=err,
        resolver_path=_fake_launcher(),
    )
    _assert_success(rc=rc, out=out, err=err, expectation=expectation)


def test_profile_conf_fresh_session_under_workspace_coalesces(tmp_path) -> None:
    """Ruling: fresh conf coalesces the redundant session write root.

    The canonical live-session dir sits beneath the admitted conf-workspace
    write root (runs/<id>/provider_sessions/<key>), so the helper must
    NOT install a separate overlapping `session` Landlock rule; the workspace
    authority already permits the journal writes. The launch still binds the
    session identity, path, visit key, and journal in the frame, and the
    journal write succeeds with no overlapping write-root pair.
    """
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    conf_root = _make_conf(tmp_path)
    pin = _launcher_pin()
    session_dir = (
        workspace_path / ".orchestrate" / "runs" / "run-1"
        / "provider_sessions" / VISIT_KEY
    )
    session_dir.mkdir(parents=True)
    session_dir.chmod(0o700)
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root),
                         session_dir=str(session_dir))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="conf", env=env, conf_root=str(conf_root),
        session_dir=str(session_dir), visit_key=VISIT_KEY, persistence="fresh",
    )

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(probe=True), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    empty_cwd = run_env[omp_launch_policy.EMPTY_CWD_ENV]
    child_args = json.loads(reports["ARGS"][0])
    assert child_args[:-1] == [
        "-p", "--mode", "json", "--no-title", "--no-extensions", "--no-skills",
        "--no-rules", "--model", MODEL, "--approval-mode", "write",
        "--cwd", empty_cwd, "--add-dir", str(workspace_path), "--session-dir",
    ]
    assert re.fullmatch(r"/proc/self/fd/[0-9]+", child_args[-1])
    # The workspace write root covers the nested session dir: probe writes
    # succeed there, and no separate session rule exists to overlap it.
    _profile_assertions(reports, env, home, "conf", empty_cwd=empty_cwd,
                        session_dir=str(session_dir),
                        workspace_add=True, conf_root=str(conf_root))
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    assert journal.is_file(), "the fresh conf journal must be written under the workspace root"
    frame = _assert_success(rc=rc, out=out, err=err, expectation=expectation)
    assert frame["session"] == {
        "id": SESSION_ID, "visit_key": VISIT_KEY,
        "primary_relpath": journal.name,
        "primary_sha256": _sha256_file(journal),
    }
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}
    assert frame["confinement"] == {
        "schema_version": "omp_write_confinement.v1",
        "landlock_abi": omp_launch.landlock_abi(),
        "policy_sha256": expectation.confinement_policy_sha256,
    }


def test_planted_fd_not_inherited(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    planted = socket.socketpair()[0]
    try:
        for argv in (_adapter_argv("omp"), _adapter_argv("omp_no_tools")):
            out, err = io.BytesIO(), io.StringIO()
            rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(),
                      pin=_launcher_pin(), out=out, err=err, resolver_path=_fake_launcher())
            assert rc == 0, err.getvalue()
            fds = json.loads(_reports(err.getvalue())["FDS"][0])
            assert str(planted.fileno()) not in fds
    finally:
        planted.close()


def test_no_spool_and_repeated_agent_discovery(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    conf = _make_conf(tmp_path)
    (conf / "agent" / "agents").mkdir(parents=True)
    (conf / "agent" / "agents" / "custom.md").write_text(
        "---\nname: custom\ndescription: test agent\n---\nbody\n",
        encoding="utf-8",
    )

    before = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
    journals = set()
    # R5: each fresh run owns exactly one direct journal per session dir, so
    # the repeated discovery launch uses its own fresh visit directory.
    for index, (control, run_dir) in enumerate((
        (_control(), session_dir),
        (_control(ts="2026-08-24T01:02:03.456Z"), _live_dir(tmp_path, key="step-1__v2b")),
    )):
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(run_dir),
                                     conf_root=str(conf)),
                  env=env, workspace=workspace_path, stdin=control, pin=pin,
                  out=out, err=err, resolver_path=_fake_launcher())
        assert rc == 0, err.getvalue()
        assert json.loads(_reports(err.getvalue())["AGENTS"][0]) == ["custom.md"]
    journals = {
        str(session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"),
        str(tmp_path / "visits" / "step-1__v2b" / f"2026-08-24T01-02-03-456Z_{SESSION_ID}.jsonl"),
    }
    after = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
    private_prefix = str(tmp_path / "cache" / "omp-i1" / "private")
    new_files = {p for p in (after - before) if not p.startswith(private_prefix)}
    assert new_files == journals
    assert sorted(entry.name for entry in session_dir.iterdir()) == [f"{TS_STEM}_{SESSION_ID}.jsonl"]
    # R2: the child discovers the MATERIALIZED conf inside the attempt tree,
    # never the caller's live agent dir, and the attempt tree is removed at
    # run end (no spool across repeated launches).
    assert sorted(entry.name for entry in (home / ".omp" / "agent").iterdir()) == ["agents"]
    assert sorted(entry.name for entry in (home / ".omp" / "agent" / "agents").iterdir()) == ["custom.md"]
    attempts = list((tmp_path / "cache" / "omp-i1" / "attempts").rglob("omp-attempt-*"))
    assert attempts == [], f"attempt trees must not accumulate: {attempts}"


# ---------------------------------------------------------------------------
# Binary verification and version probe
# ---------------------------------------------------------------------------


def test_source_verification_failures(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _fake_pin()

    def _fails(path, needle, pin_override=None):
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
                  stdin=_control(), pin=pin if pin_override is None else pin_override,
                  out=out, err=err, resolver_path=path)
        assert rc == 2, (rc, err.getvalue())
        assert needle in err.getvalue(), err.getvalue()
        assert b"orchestrator.omp_launch.v1" not in out.getvalue()

    link = tmp_path / "link-omp"
    link.symlink_to(_FAKE_SOURCE)
    _fails(link, "no-follow")
    _fails(tmp_path / "data", "regular file")
    writable = tmp_path / "writable-omp"
    writable.write_bytes(_FAKE_SOURCE.read_bytes())
    writable.chmod(0o666)
    _fails(writable, "writable")
    _fails(
        _fake_launcher(),
        "digest",
        dataclasses.replace(_launcher_pin(), executable_sha256="0" * 64),
    )


def test_version_probe_contract_and_drift(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp"),
        env=env,
        workspace=workspace_path,
        stdin=_control(),
        pin=dataclasses.replace(pin, version="999.0.0"),
        out=out,
        err=err,
        resolver_path=_fake_launcher(),
    )
    assert rc == 2
    assert "version probe" in err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_missing_write_root_fails_before_child(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env.pop("TMPDIR")

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_fake_pin(), out=out, err=err)
    assert rc == 2
    assert "TMPDIR" in err.getvalue()
    assert "FAKE_" not in err.getvalue(), "child must never run when setup fails"


def test_helper_rejects_bad_roots_digest_and_target(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    roots = _env_roots(env)
    private = _private_fixture(
        tmp_path / "private",
        _fake_pin().executable_sha256,
        _FAKE_SOURCE.read_bytes(),
    )
    (tmp_path / "empty").mkdir()

    base = [
        "--abi", "3", "--digest", "0" * 64,
        "--protected", f"omp-home={home / '.omp'}",
        "--write", f"data={roots['data']}", "--write", f"state={roots['state']}",
        "--write", f"cache={roots['cache']}", "--write", f"temp={roots['temp']}",
        "--read", f"cwd={tmp_path / 'empty'}",
        "--", str(private), "--version",
    ]

    def _fails(argv, needle):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = helper_main(argv)
        assert rc == 2, (rc, argv)
        assert needle in err.getvalue(), err.getvalue()

    _fails(["--abi", "2", *base[2:]], "exactly Landlock ABI 3")
    _fails(["--abi", "x", *base[2:]], "expected --abi N")
    _fails(["--abi", "4", *base[2:]], "exactly Landlock ABI 3")
    _fails(base[2:], "expected --abi N")
    sep = base.index("--")
    dup = base[:sep] + ["--write", f"session={tmp_path / 'visits'}",
                        "--write", f"session={tmp_path / 'visits'}"] + base[sep:]
    _fails(dup, "duplicate write role")
    extra = base[:sep] + ["--write", f"bogus={roots['temp']}"] + base[sep:]
    _fails(extra, "unknown write role")
    _fails(base[:sep] + ["--write", f"data={roots['data']}"] + base[sep:], "exactly one each")
    _fails(["--abi", "3", "--digest", "0" * 64, "--", str(private), "--version"],
           "missing fixed protected roots")
    _fails(base, "canonical policy digest does not match")
    bad_target = [t for t in base]
    bad_target[bad_target.index("--") + 1] = str(tmp_path / "fake_omp.py")
    (tmp_path / "fake_omp.py").write_bytes(_FAKE_SOURCE.read_bytes())
    _fails(bad_target, "digest-named launch attempt")


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_conf_runtime_mutation_fails_at_close(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    conf_root = _make_conf(tmp_path)
    pin = _launcher_pin()

    out, err = io.BytesIO(), io.StringIO()
    result: dict[str, int] = {}

    def _blocking() -> None:
        result["rc"] = _run(argv=_adapter_argv("omp_conf", conf_root=str(conf_root)),
                            env=env, workspace=workspace_path, stdin=_control(sleep=1.5),
                            pin=pin, out=out, err=err, resolver_path=_fake_launcher())

    thread = threading.Thread(target=_blocking)
    thread.start()
    time.sleep(0.6)
    (conf_root / "agent" / "WATCHDOG.yml").parent.mkdir(exist_ok=True)
    (conf_root / "agent" / "WATCHDOG.yml").write_text(
        "instructions: drift\nadvisors:\n  - name: w\n    model: m\n    tools: [read]\n"
        "    instructions: x\n    enabled: true\n",
        encoding="utf-8",
    )
    thread.join(timeout=30)

    assert result.get("rc", -1) != 0
    assert "conf" in err.getvalue().lower()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_primary_mismatch_fails_without_frame(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    session_dir = _live_dir(tmp_path)

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(session_dir)),
              env=env, workspace=workspace_path,
              stdin=_control(mode="primary-mismatch", journal_id="other-id"),
              pin=_launcher_pin(), out=out, err=err, resolver_path=_fake_launcher())
    assert rc == 2
    assert "primary" in err.getvalue().lower()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_unsettled_and_nonzero_child(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(mode="unsettled"), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 1
    assert "settle" in err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(exit=3), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 3
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_spoofed_frame_rejected_by_accumulator(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    argv = _adapter_argv("omp")
    spoof = ('{"type":"orchestrator.omp_launch.v1","lane":"omp","persistence":"none",'
             '"binary":{},"child":{},"session":{},"conf":{},"confinement":null,"observed":{}}')

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path,
              stdin=_control(mode="spoof", spoof_line=spoof), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 1
    assert out.getvalue().count(b'"type":"orchestrator.omp_launch.v1"') == 1
    assert "did not settle" in err.getvalue()


def _real_binary_resolver(tmp_path):
    """R1: resolve the real pinned build from PATH (hard link, never symlink).

    The source must be a regular file owned by the effective user; symlinks
    are rejected by the resolver, so the test stages a hard link exactly like
    a deployed install.
    """
    installed = Path.home() / ".local" / "bin" / "omp"
    bindir = tmp_path / "real-bin"
    bindir.mkdir()
    if not installed.is_file():
        pytest.skip("real pinned build not installed at ~/.local/bin/omp")
    if _sha256_file(installed) != OMP_BINARY_PIN.executable_sha256:
        pytest.skip("installed omp is not the pinned acceptance build (R1 refuses)")
    # copy (not hard link): the installed home may be on another filesystem
    shutil.copyfile(installed, bindir / "omp")
    bindir.joinpath("omp").chmod(0o555)
    return bindir




@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_real_pinned_binary_no_tools_transient_completes(tmp_path) -> None:


    """Real profile completion requires a live operator-supplied auth broker."""
    broker_url = os.environ.get("OMP_AUTH_BROKER_URL")
    broker_token = os.environ.get("OMP_AUTH_BROKER_TOKEN")
    if not broker_url or not broker_token:
        pytest.skip("live OMP auth broker pair is not configured")
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env.update({
        "OMP_AUTH_BROKER_URL": broker_url,
        "OMP_AUTH_BROKER_TOKEN": broker_token,
    })
    bindir = _real_binary_resolver(tmp_path)
    assert bindir is not None
    env["PATH"] = f"{bindir}:{env['PATH']}"
    argv = _adapter_argv("omp_no_tools")
    expectation, run_env = _frozen_profile_expectation(
        OMP_BINARY_PIN, argv, lane="no-tools", env=env,
        conf_root=str(omp_launch.neutral_conf_root()),
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv, env=run_env, workspace=workspace_path,
        stdin=b"Reply with exactly: PROFILE-NO-TOOLS-OK\n",
        pin=OMP_BINARY_PIN, out=out, err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(run_env),
    )
    assert rc == 0, err.getvalue()
    child_bytes, frame = _frame_bytes(out.getvalue())
    session_id = json.loads(child_bytes.splitlines()[0])["id"]
    accumulator = OmpJsonStdoutAccumulator(
        expectation=dataclasses.replace(
            expectation, stdout_session_id=session_id))
    accumulator.feed(out.getvalue())
    metadata, error = accumulator.finalize(
        expected_session_id=session_id, require_terminal=True)
    assert error is None and metadata is not None, error
    assert frame["lane"] == "no-tools"
    assert frame["persistence"] == "none"
    assert frame["child"]["exit_code"] == 0


@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_real_pinned_binary_conf_fresh_completes(tmp_path) -> None:
    broker_url = os.environ.get("OMP_AUTH_BROKER_URL")
    broker_token = os.environ.get("OMP_AUTH_BROKER_TOKEN")
    if not broker_url or not broker_token:
        pytest.skip("live OMP auth broker pair is not configured")
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env.update({
        "OMP_AUTH_BROKER_URL": broker_url,
        "OMP_AUTH_BROKER_TOKEN": broker_token,
    })
    bindir = _real_binary_resolver(tmp_path)
    assert bindir is not None
    env["PATH"] = f"{bindir}:{env['PATH']}"
    conf_root = _make_conf(tmp_path)
    conf_bytes = (conf_root / "config.yml").read_bytes()
    session_dir = _live_dir(tmp_path, "real-conf__v1")
    argv = _adapter_argv(
        "omp_conf", conf_root=str(conf_root),
        session_dir=str(session_dir),
    )
    expectation, run_env = _frozen_profile_expectation(
        OMP_BINARY_PIN, argv, lane="conf", env=env,
        conf_root=str(conf_root), session_dir=str(session_dir),
        visit_key=session_dir.name, persistence="fresh",
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=argv, env=run_env, workspace=workspace_path,
        stdin=b"Reply with exactly: PROFILE-CONF-OK\n",
        pin=OMP_BINARY_PIN, out=out, err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(run_env),
    )
    assert rc == 0, err.getvalue()
    child_bytes, frame = _frame_bytes(out.getvalue())
    session_id = json.loads(child_bytes.splitlines()[0])["id"]
    accumulator = OmpJsonStdoutAccumulator(
        expectation=dataclasses.replace(
            expectation, stdout_session_id=session_id))
    accumulator.feed(out.getvalue())
    metadata, error = accumulator.finalize(
        expected_session_id=session_id, require_terminal=True)
    assert error is None and metadata is not None, error
    assert frame["lane"] == "conf"
    assert frame["persistence"] == "fresh"
    assert frame["session"]["visit_key"] == session_dir.name
    assert frame["session"]["primary_relpath"]
    assert (conf_root / "config.yml").read_bytes() == conf_bytes


# The real pinned acceptance build needs the real auth home (agent.db with the
# stored provider credentials); both ambient smokes make one real model call.
def _real_auth_home() -> str:
    """Portable real auth home; skip when no validated credential state.

    Honors ``OMP_E2E_AUTH_HOME`` explicitly; otherwise accepts the current
    HOME only after it carries the OMP agent credential store. Never hardcodes
    a developer path.
    """
    from tests.test_omp_integration import real_auth_home

    home = real_auth_home()
    if home is None:
        pytest.skip(
            "no validated real auth home (set OMP_E2E_AUTH_HOME or provide "
            "the OMP agent credential store under $HOME/.omp/agent)"
        )
    return str(home)


@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_real_pinned_binary_ambient_transient_completes(tmp_path) -> None:
    """Real pinned binary, ambient transient lane: a real session completes
    through the adapter with the OMP JSON transport on stdout and one real
    adapter frame (lane ambient, null confinement, no session dir)."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env["HOME"] = _real_auth_home()
    bindir = _real_binary_resolver(tmp_path)
    assert bindir is not None, "real pinned build must be installed at ~/.local/bin/omp"
    env["PATH"] = f"{bindir}:{env['PATH']}"
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp"),
        env=env,
        workspace=workspace_path,
        stdin=b"Reply with exactly: SMOKE-OK\n",
        pin=OMP_BINARY_PIN,
        out=out,
        err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(env),
    )
    text = err.getvalue()
    assert rc == 0, f"rc={rc} stderr={text}"
    assert "child exited" not in text, text
    child_bytes, frame = _frame_bytes(out.getvalue())
    assert json.dumps(frame, separators=(",", ":")) in out.getvalue().decode("utf-8")
    header = json.loads(child_bytes.splitlines()[0])
    assert header["type"] == "session" and isinstance(header["id"], str) and header["id"]
    assert frame["lane"] == "ambient"
    assert frame["persistence"] == "none"
    assert frame["confinement"] is None
    assert frame["child"]["exit_code"] == 0
    assert frame["session"]["id"] == header["id"]
    assert frame["session"]["visit_key"] is None
    assert frame["session"]["primary_relpath"] is None
    assert frame["observed"]["child_relpaths"] == []


@pytest.mark.e2e
@pytest.mark.requires_secrets
def test_real_pinned_binary_ambient_fresh_completes(tmp_path) -> None:
    """Real pinned binary, ambient fresh lane: the exclusive live session dir
    receives the child-written journal; the adapter scans it and frames the
    real session id and primary journal (relpath + sha256)."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env["HOME"] = _real_auth_home()
    bindir = _real_binary_resolver(tmp_path)
    assert bindir is not None, "real pinned build must be installed at ~/.local/bin/omp"
    env["PATH"] = f"{bindir}:{env['PATH']}"
    live = tmp_path / "visits" / "v1"
    live.mkdir(parents=True)
    live.chmod(0o700)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp", session_dir=str(live)),
        env=env,
        workspace=workspace_path,
        stdin=b"Reply with exactly: SMOKE-OK\n",
        pin=OMP_BINARY_PIN,
        out=out,
        err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(env),
    )
    text = err.getvalue()
    assert rc == 0, f"rc={rc} stderr={text}"
    assert "child exited" not in text, text
    child_bytes, frame = _frame_bytes(out.getvalue())
    assert json.dumps(frame, separators=(",", ":")) in out.getvalue().decode("utf-8")
    header = json.loads(child_bytes.splitlines()[0])
    assert header["type"] == "session" and isinstance(header["id"], str) and header["id"]
    assert frame["lane"] == "ambient"
    assert frame["persistence"] == "fresh"
    assert frame["confinement"] is None
    assert frame["child"]["exit_code"] == 0
    assert frame["session"]["id"] == header["id"]
    assert frame["session"]["visit_key"] == "v1"
    primary = frame["session"]["primary_relpath"]
    assert isinstance(primary, str) and primary.endswith(".jsonl"), frame
    assert primary.rsplit("_", 1)[-1][: -len(".jsonl")] == header["id"], frame
    assert _HEX64_RE.fullmatch(frame["session"]["primary_sha256"]), frame
    advisors = frame["observed"]["advisor_relpaths"]
    assert advisors and all(path.endswith("/__advisor.jsonl") for path in advisors), frame
    assert frame["observed"]["child_relpaths"] == [], frame
    assert primary not in advisors, frame


# ---------------------------------------------------------------------------
# Task 5 review fix round: findings 1-4, 6, 7, 9 (RED-first regression suite)
# ---------------------------------------------------------------------------


def _helper_base(home: Path, env: dict, tmp_path: Path) -> tuple[list[str], Path]:
    """Helper argv with a REAL digest over the same roots the adapter uses."""
    roots = _env_roots(env)
    private = _private_fixture(
        tmp_path / "private",
        _fake_pin().executable_sha256,
        _FAKE_SOURCE.read_bytes(),
    )
    (tmp_path / "empty").mkdir()
    digest = canonical_policy_digest(
        lane="no-tools", home_omp=str(home / ".omp"), session_dir=None,
        conf_root=str(omp_launch.neutral_conf_root()), workspace=str(workspace_path),
        empty_cwd=str(tmp_path / "empty"), env_roots=roots,
    )
    base = [
        "--abi", "3", "--digest", digest,
        "--protected", f"omp-home={home / '.omp'}",
        "--write", f"data={roots['data']}", "--write", f"state={roots['state']}",
        "--write", f"cache={roots['cache']}", "--write", f"temp={roots['temp']}",
        "--read", f"conf={omp_launch.neutral_conf_root()}",
        "--read", f"cwd={tmp_path / 'empty'}",
        "--", str(private), "--version",
    ]
    return base, private


def _helper_fails(argv: list[str], needle: str) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "orchestrator.providers.omp_write_confinement", *argv],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert needle in proc.stderr, proc.stderr
    return proc.stderr


def test_helper_mask_is_the_exact_abi3_mutation_set() -> None:
    from orchestrator.providers.omp_write_confinement import MUTATION_FS_RIGHTS
    # 0x77F2 (old) omitted MAKE_BLOCK (0x800); the ABI-3 mutation-only set is
    # WRITE_FILE|REMOVE_DIR|REMOVE_FILE|MAKE_CHAR|MAKE_DIR|MAKE_REG|MAKE_SOCK|
    # MAKE_FIFO|MAKE_BLOCK|MAKE_SYM|REFER|TRUNCATE.
    assert MUTATION_FS_RIGHTS == 0x7FF2


def test_helper_exact_mask_is_accepted_by_this_kernel() -> None:
    from orchestrator.providers.omp_write_confinement import ConfinementError, _validate_exact_mask
    _validate_exact_mask()  # raises ConfinementError on a rejecting kernel


def test_helper_landlock_abi_queries_the_version_directly(monkeypatch) -> None:
    from orchestrator.providers import omp_write_confinement as wc

    class _Libc:
        def __init__(self, _name, **kwargs):
            pass

        def syscall(self, number, attr, size, flags):
            # The direct VERSION query passes a null ruleset-attr pointer.
            if attr is None and flags == wc._LANDLOCK_CREATE_RULESET_VERSION:
                return 3  # exact ABI 3
            return -1  # any mask probe fails: the exact-mask probe must reject

    monkeypatch.setattr(wc.ctypes, "CDLL", _Libc)
    assert wc.landlock_abi() == 3
    with pytest.raises(wc.ConfinementError):
        wc._validate_exact_mask()


def test_helper_rejects_old_fd_grammar_and_opens_the_private_path_itself(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _helper_base(home, env, tmp_path)
    _helper_fails(["--abi", "3", "--digest", "0" * 64, "--fd", "3", *base[2:]],
                  "unexpected helper argument")


def test_helper_rejects_non_private_copy_directory(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _helper_base(home, env, tmp_path)
    _private.parent.chmod(0o777)
    _helper_fails(base, "private copy directory")


def _overlap_argv(home: Path, env: dict, tmp_path: Path, **root_mutations: str):
    """Helper argv whose digest matches a mutated write-root set."""
    roots = {**_env_roots(env), **root_mutations}
    launcher = _fake_launcher()  # native ELF: fd-exec refuses shebang scripts
    digest_dir = _sha256_file(launcher)
    private = _private_fixture(
        tmp_path / "private", digest_dir, launcher.read_bytes()
    )
    (tmp_path / "empty").mkdir()
    digest = canonical_policy_digest(
        lane="no-tools", home_omp=str(home / ".omp"), session_dir=None,
        conf_root=str(omp_launch.neutral_conf_root()), workspace=str(workspace_path),
        empty_cwd=str(tmp_path / "empty"), env_roots=roots,
    )
    from orchestrator.providers.omp_write_confinement import SYSTEM_RUNTIME_ROOTS
    argv = [
        "--abi", "3", "--digest", digest,
        "--protected", f"omp-home={home / '.omp'}",
    ]
    argv += [flag for root in SYSTEM_RUNTIME_ROOTS for flag in ("--protected", f"system-runtime={root}")]
    argv += [
        "--write", f"data={roots['data']}", "--write", f"state={roots['state']}",
        "--write", f"cache={roots['cache']}", "--write", f"temp={roots['temp']}",
        "--read", f"conf={omp_launch.neutral_conf_root()}",
        "--read", f"cwd={tmp_path / 'empty'}",
        "--", str(private), "--version",
    ]
    return argv, private


def test_helper_rejects_write_overlap_with_omp_home(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _overlap_argv(home, env, tmp_path, data=str(home / ".omp"))
    _helper_fails(base, "duplicate opened root identity")


def test_helper_rejects_write_overlap_with_conf_root(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _overlap_argv(
        home, env, tmp_path, data=str(omp_launch.neutral_conf_root())
    )
    _helper_fails(base, "duplicate opened root identity")


def test_helper_rejects_write_overlap_with_cwd_root(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _overlap_argv(home, env, tmp_path, temp=str(tmp_path / "empty"))
    _helper_fails(base, "duplicate opened root identity")


def test_helper_rejects_write_root_containing_omp_home(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _overlap_argv(home, env, tmp_path, data=str(home))
    _helper_fails(base, "overlaps opened omp-home")


def test_helper_rejects_nested_write_state_under_data(tmp_path) -> None:
    """T5-SEC-003: a write root nested below another write root is rejected.

    The brief's overlapping-write-root failure is not limited to protected or
    read roots: ``state`` below ``data`` must fail before confinement in both
    the lexical prefilter and the opened-identity relation check.
    """
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    nested = Path(env["XDG_DATA_HOME"]) / "state"
    nested.mkdir(parents=True)
    base, _private = _overlap_argv(home, env, tmp_path, state=str(nested))
    _helper_fails(base, "overlaps")


def test_helper_rejects_nested_write_data_under_state(tmp_path) -> None:
    """Reverse relation direction: ``data`` below ``state`` is also rejected."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    nested = Path(env["XDG_STATE_HOME"]) / "data"
    nested.mkdir(parents=True)
    base, _private = _overlap_argv(home, env, tmp_path, data=str(nested))
    _helper_fails(base, "overlaps")


def test_adapter_rejects_symlink_at_empty_cwd_path(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _fake_pin()
    target = tmp_path / "real-empty"
    target.mkdir()
    empty = omp_launch.empty_omp_cwd(
        home=str(home), lane="no-tools", workspace=str(workspace_path),
        session_dir=None, conf_root=str(omp_launch.neutral_conf_root()),
        env_roots=_env_roots(env),
    )
    os.symlink(str(target), empty)  # preplanted symlink at the cwd path

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err)
    assert rc == 2, err.getvalue()
    assert "empty" in err.getvalue().lower(), err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_adapter_rejects_preexisting_nonempty_empty_cwd(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _fake_pin()
    empty = omp_launch.empty_omp_cwd(
        home=str(home), lane="no-tools", workspace=str(workspace_path),
        session_dir=None, conf_root=str(omp_launch.neutral_conf_root()),
        env_roots=_env_roots(env),
    )
    os.makedirs(empty)
    (Path(empty) / "planted").write_text("x", encoding="utf-8")

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err)
    assert rc == 2, err.getvalue()
    assert "empty" in err.getvalue().lower(), err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_adapter_relay_redacts_the_profile_broker_token(tmp_path) -> None:
    """R2: the relay redacts the real operator token in a profile lane."""
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools", conf_root=str(omp_launch.neutral_conf_root())),
              env=env, workspace=workspace_path,
              stdin=_control(leak_token=True), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    text = err.getvalue()
    assert "TOKEN_LEAK [redacted]" in text, text
    assert "caller-token-must-not-leak" not in text, text
    assert "caller-token-must-not-leak" not in out.getvalue().decode("utf-8"), out


def test_adapter_relay_redacts_an_inherited_ambient_broker_token(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp"),
        env=env,
        workspace=workspace_path,
        stdin=_control(leak_token=True),
        pin=_launcher_pin(),
        out=out,
        err=err,
        resolver_path=_fake_launcher(),
    )

    assert rc == 0, err.getvalue()
    assert "TOKEN_LEAK [redacted]" in err.getvalue()
    assert "caller-token-must-not-leak" not in err.getvalue()


def test_adapter_fresh_session_rejects_symlink_journal_entry(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    real = tmp_path / "real.jsonl"
    real.write_text("{}", encoding="utf-8")
    os.symlink(str(real), session_dir / f"{TS_STEM}_zzz.jsonl")

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(session_dir)),
              env=env, workspace=workspace_path, stdin=_control(),
              pin=pin, out=out, err=err)
    assert rc == 2, err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_primary_journal_identity_rejects_symlink_and_huge_journal(tmp_path) -> None:
    from orchestrator.providers.omp_launch_fs import (
        LaunchFsError,
        primary_journal_identity,
    )

    session_dir = tmp_path / "visits"
    session_dir.mkdir()
    real = tmp_path / "r.jsonl"
    real.write_text("x", encoding="utf-8")
    os.symlink(str(real), session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl")
    with pytest.raises(LaunchFsError):
        primary_journal_identity(str(session_dir), SESSION_ID)
    os.unlink(session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl")

    huge = session_dir / f"2026-01-01T00-00-00-000Z_{SESSION_ID}.jsonl"
    with open(huge, "wb") as handle:
        handle.truncate(512 * 1024 * 1024 + 1)  # sparse; over the hash bound
    with pytest.raises(LaunchFsError):
        primary_journal_identity(str(session_dir), SESSION_ID)


# ---------------------------------------------------------------------------
# Task 5 fix round 2: RED-first regression suite (re-review findings 1-8)
# ---------------------------------------------------------------------------


def test_ambient_exec_is_not_mutable_after_verify(tmp_path, monkeypatch) -> None:
    """T5-SEC-001: the ambient child must exec the verified fd, not a pathname.

    A same-UID swap of the private digest-named copy between verification and
    the child spawn must never run: the launch fails closed instead of
    executing the swapped bytes.
    """
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    evil = tmp_path / "evil_omp.py"
    evil.write_text("print('SWAPPED_MARKER')\n", encoding="utf-8")
    evil_launcher = _compile_launcher(evil)
    private_root = (
        Path(env["XDG_CACHE_HOME"])
        / "omp-i1"
        / "private"
        / pin.executable_sha256
    )

    import subprocess as _subprocess

    real_popen = _subprocess.Popen

    def _swapping_popen(args, *a, **kw):
        argv = list(args) if isinstance(args, (list, tuple)) else [args]
        private = next(
            (
                Path(arg)
                for arg in argv
                if isinstance(arg, str)
                and arg.startswith(f"{private_root}{os.sep}attempt-")
                and arg.endswith(f"{os.sep}omp")
            ),
            None,
        )
        if "--version" not in argv and private is not None:
            private.chmod(0o700)
            private.write_bytes(evil_launcher.read_bytes())
            private.chmod(0o500)
            assert private.read_bytes() == evil_launcher.read_bytes()
        return real_popen(args, *a, **kw)

    monkeypatch.setattr(_subprocess, "Popen", _swapping_popen)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    text = out.getvalue().decode("utf-8", errors="replace")
    assert "SWAPPED_MARKER" not in text, text
    assert rc != 0, "a swapped private copy must fail closed, never run"


def test_helper_rejects_duplicate_opened_root_identity(tmp_path) -> None:
    """T5-SEC-003: opened (dev, ino) identities must be unique across roots."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    base, _private = _overlap_argv(home, env, tmp_path, cache=env["XDG_DATA_HOME"])
    _helper_fails(base, "duplicate")


def _symlink_root_argv(home: Path, env: dict, tmp_path: Path, data_path: Path):
    """Helper argv over one symlinked write root.

    The digest is frozen the way a pre-fix parent would freeze it (over the
    realpath-resolved directory identity); the helper's no-follow component
    walk must reject the symlinked root regardless.
    """
    roots = {**_env_roots(env), "data": str(data_path)}
    resolved_data = os.path.realpath(str(data_path))
    digest_roots = {**roots, "data": resolved_data}
    private = _private_fixture(
        tmp_path / "private",
        _fake_pin().executable_sha256,
        _FAKE_SOURCE.read_bytes(),
    )
    (tmp_path / "empty").mkdir()
    digest = canonical_policy_digest(
        lane="no-tools", home_omp=str(home / ".omp"), session_dir=None,
        conf_root=str(omp_launch.neutral_conf_root()), workspace=str(workspace_path),
        empty_cwd=str(tmp_path / "empty"), env_roots=digest_roots,
    )
    from orchestrator.providers.omp_write_confinement import SYSTEM_RUNTIME_ROOTS
    argv = [
        "--abi", "3", "--digest", digest,
        "--protected", f"omp-home={home / '.omp'}",
    ]
    argv += [flag for root in SYSTEM_RUNTIME_ROOTS for flag in ("--protected", f"system-runtime={root}")]
    argv += [
        "--write", f"data={roots['data']}", "--write", f"state={roots['state']}",
        "--write", f"cache={roots['cache']}", "--write", f"temp={roots['temp']}",
        "--read", f"conf={omp_launch.neutral_conf_root()}",
        "--read", f"cwd={tmp_path / 'empty'}",
        "--", str(private), "--version",
    ]
    return argv, private


def test_digest_rejects_symlink_roots(tmp_path) -> None:
    """T5-SEC-003: the parent-side digest must fail closed on a symlinked root."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    real = tmp_path / "real-data"
    real.mkdir()
    link = tmp_path / "data-link"
    link.symlink_to(real)
    roots = {**_env_roots(env), "data": str(link)}
    (tmp_path / "empty").mkdir()
    with pytest.raises(Exception):
        canonical_policy_digest(
            lane="no-tools", home_omp=str(home / ".omp"), session_dir=None,
            conf_root=str(omp_launch.neutral_conf_root()), workspace=str(workspace_path),
            empty_cwd=str(tmp_path / "empty"), env_roots=roots,
        )


def test_helper_rejects_symlink_final_root(tmp_path) -> None:
    """T5-SEC-003: a final-component symlink root must fail the no-follow open."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    real = tmp_path / "real-data"
    real.mkdir()
    link = tmp_path / "data-link"
    link.symlink_to(real)
    base, _private = _symlink_root_argv(home, env, tmp_path, link)
    _helper_fails(base, "cannot open")


def test_helper_rejects_symlink_intermediate_root(tmp_path) -> None:
    """T5-SEC-003: an intermediate-component symlink root must fail closed."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    parent = tmp_path / "real-parent"
    parent.mkdir()
    (parent / "data").mkdir()
    link_parent = tmp_path / "link-parent"
    link_parent.symlink_to(parent)
    base, _private = _symlink_root_argv(home, env, tmp_path, link_parent / "data")
    _helper_fails(base, "cannot open")


def test_helper_root_open_is_race_closed(tmp_path) -> None:
    """T5-SEC-003: replacing a designated root with a symlink fails closed."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    target = tmp_path / "race-target"
    target.mkdir()
    data = tmp_path / "race-data"
    data.mkdir()  # a real directory at digest time
    base, _private = _symlink_root_argv(home, env, tmp_path, data)
    os.rmdir(data)
    data.symlink_to(target)  # replaced between freeze and open
    proc = subprocess.run(
        [sys.executable, "-m", "orchestrator.providers.omp_write_confinement", *base],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert "cannot open" in proc.stderr, proc.stderr
    assert b"orchestrator.omp_launch.v1" not in b"".join(
        [proc.stdout.encode("utf-8")]
    ), "the helper must never emit a launch frame"



def test_adapter_rejects_non_private_session_dir(tmp_path) -> None:
    """T5-SEC-005: the adapter must not bless a group/other-accessible live dir."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    session_dir = _live_dir(tmp_path)
    session_dir.chmod(0o755)  # group/other accessible
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(session_dir)),
              env=env, workspace=workspace_path, stdin=_control(),
              pin=_launcher_pin(), out=out, err=err, resolver_path=_fake_launcher())
    assert rc == 2, err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_primary_journal_identity_rejects_hardlinked_journal(tmp_path) -> None:
    """T5-SEC-006: a primary journal must be a one-link regular file."""
    from orchestrator.providers.omp_launch_fs import (
        LaunchFsError,
        primary_journal_identity,
    )

    session_dir = tmp_path / "visits"
    session_dir.mkdir()
    session_dir.chmod(0o700)
    source = tmp_path / "s.jsonl"
    source.write_text("x", encoding="utf-8")
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    os.link(source, journal)
    with pytest.raises(LaunchFsError):
        primary_journal_identity(str(session_dir), SESSION_ID)


def test_parent_revalidates_primary_journal_against_frame(tmp_path) -> None:
    """T5-SEC-006: the parent re-derives the primary and compares to the frame."""
    from orchestrator.providers.omp_launch_fs import (
        LaunchFsError,
        primary_journal_identity,
        revalidate_primary_journal,
    )

    session_dir = tmp_path / "visits"
    session_dir.mkdir()
    session_dir.chmod(0o700)
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    journal.write_text("original bytes", encoding="utf-8")
    relpath, sha = primary_journal_identity(str(session_dir), SESSION_ID)
    assert relpath == journal.name
    assert _HEX64_RE.fullmatch(sha)
    # No drift: the parent's re-derivation agrees with the adapter's frame.
    revalidate_primary_journal(str(session_dir), SESSION_ID, relpath, sha)
    # The journal changed after the adapter framed it: the parent must reject.
    journal.write_text("modified bytes", encoding="utf-8")
    with pytest.raises(LaunchFsError):
        revalidate_primary_journal(str(session_dir), SESSION_ID, relpath, sha)


def test_adapter_cleans_empty_cwd_on_pre_child_failure(tmp_path) -> None:
    """T5-SEC-002: the adapter removes the empty cwd when setup fails pre-child."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    empty = omp_launch.empty_omp_cwd(
        home=str(home), lane="no-tools", workspace=str(workspace_path),
        session_dir=None, conf_root=str(omp_launch.neutral_conf_root()),
        env_roots=_env_roots(env),
    )
    pin = dataclasses.replace(_launcher_pin(), version="999.0.0")
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 2, err.getvalue()
    assert not os.path.exists(empty), "the adapter must remove the empty cwd on failure"


# ---------------------------------------------------------------------------
# Task 5 fix round 3: RED-first regression suite (findings 1-7)
# ---------------------------------------------------------------------------
# Internal carrier names (must match omp_launch_fs.CARRIER_ENV_NAMES after the
# fix; written as literals so the REDs fail on behavior, not imports).
_CARRIER_EMPTY_CWD = "_OMP_I1_EMPTY_CWD"
_CARRIER_SESSION_DIR = "_OMP_I1_SESSION_DIR"
_CARRIER_SESSION_IDENTITY = "_OMP_I1_SESSION_DIR_IDENTITY"


def test_parser_rejects_internal_empty_cwd_flag(tmp_path) -> None:
    """Finding 5: Brief Step 5.4 grammar accepts only run/lane/model/conf-root/session-dir.

    The per-invocation cwd must travel through the code-owned internal
    carrier, never through the exact private adapter argv.
    """
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools") + ["--empty-cwd", "/tmp/evil"],
              env=env, workspace=workspace_path, stdin=_control(),
              pin=_fake_pin(), out=out, err=err)
    assert rc == 2, (rc, err.getvalue())
    assert "unexpected" in err.getvalue(), err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_ambient_fresh_rejects_mismatched_session_identity_before_child(tmp_path) -> None:
    """Finding 2 (T5-SEC-005): the ambient adapter compares the frozen
    identity BEFORE the child runs; a mismatched carrier fails closed."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    session_dir = _live_dir(tmp_path)
    env = {**env, _CARRIER_SESSION_IDENTITY: "1:1"}  # wrong identity
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp", session_dir=str(session_dir)),
              env=env, workspace=workspace_path, stdin=_control(),
              pin=_launcher_pin(), out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 2, (rc, err.getvalue())
    assert "identity" in err.getvalue().lower(), err.getvalue()
    assert "FAKE_" not in err.getvalue(), "the child must never run on identity mismatch"


def test_profile_helper_rejects_mismatched_session_identity(tmp_path) -> None:
    """Finding 2 (T5-SEC-005): the confined helper compares its retained
    session-root fd before add_rule/exec; a mismatched carrier fails closed."""
    from orchestrator.providers.omp_write_confinement import SYSTEM_RUNTIME_ROOTS

    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    roots = _env_roots(env)
    session_dir = _live_dir(tmp_path)
    private = _private_fixture(
        tmp_path / "private",
        _fake_pin().executable_sha256,
        _FAKE_SOURCE.read_bytes(),
    )
    (tmp_path / "empty").mkdir()
    digest = canonical_policy_digest(
        lane="no-tools", home_omp=str(home / ".omp"), session_dir=str(session_dir),
        conf_root=str(omp_launch.neutral_conf_root()), workspace=str(workspace_path),
        empty_cwd=str(tmp_path / "empty"), env_roots=roots,
    )
    argv = ["--abi", "3", "--digest", digest,
            "--protected", f"omp-home={home / '.omp'}"]
    argv += [flag for root in SYSTEM_RUNTIME_ROOTS for flag in ("--protected", f"system-runtime={root}")]
    argv += [
        "--write", f"data={roots['data']}", "--write", f"state={roots['state']}",
        "--write", f"cache={roots['cache']}", "--write", f"temp={roots['temp']}",
        "--write", f"session={session_dir}",
        "--read", f"conf={omp_launch.neutral_conf_root()}",
        "--read", f"cwd={tmp_path / 'empty'}",
        "--", str(private), "--version",
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "orchestrator.providers.omp_write_confinement", *argv],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, _CARRIER_SESSION_IDENTITY: "1:1",
             _CARRIER_SESSION_DIR: str(session_dir)},
    )
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert "identity" in proc.stderr.lower(), proc.stderr


def test_adapter_direct_seam_rejects_preplanted_empty_cwd(tmp_path) -> None:
    """Finding 4: direct mode exclusive-creates its cwd; an EMPTY preplanted
    directory at the deterministic path must fail closed, never be adopted."""
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    empty = omp_launch.empty_omp_cwd(
        home=str(home), lane="no-tools", workspace=str(workspace_path),
        session_dir=None, conf_root=str(omp_launch.neutral_conf_root()),
        env_roots=_env_roots(env),
    )
    os.makedirs(empty)  # private, EMPTY, at the deterministic path
    os.chmod(empty, 0o700)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 2, err.getvalue()
    assert "empty" in err.getvalue().lower(), err.getvalue()


def test_fresh_session_scan_is_atomic_to_one_visit_fd(tmp_path) -> None:
    """Finding 3 (T5-SEC-006): inventory + primary derive from the SAME
    retained fd as the identity compare; a whole-dir swap cannot redirect
    attribution, and reopening the path fails on the changed identity."""
    from orchestrator.providers import omp_launch_policy as policy
    from orchestrator.providers.omp_launch_fs import (
        primary_journal_identity,
        primary_journal_identity_fd,
        session_dir_identity,
        session_inventory_fd,
    )

    live = tmp_path / "v1.live"
    live.mkdir()
    live.chmod(0o700)
    expected = session_dir_identity(str(live))
    journal = live / f"{TS_STEM}_{SESSION_ID}.jsonl"
    journal.write_text("original", encoding="utf-8")
    relpath, sha = primary_journal_identity(str(live), SESSION_ID)
    fd = policy.open_session_dir_verified(str(live), expected)
    try:
        # Swap the whole visit dir; the retained fd still names the original.
        os.rename(live, tmp_path / "v1.old")
        fresh = live
        fresh.mkdir()
        fresh.chmod(0o700)
        (fresh / f"{TS_STEM}_{SESSION_ID}.jsonl").write_text(
            "attacker", encoding="utf-8"
        )
        observed = session_inventory_fd(fd)
        relpath2, sha2 = primary_journal_identity_fd(fd, SESSION_ID)
        assert observed == (journal.name,)
        assert (relpath2, sha2) == (relpath, sha)
        with pytest.raises(policy.LaunchFsError):
            policy.open_session_dir_verified(str(live), expected)
    finally:
        os.close(fd)


def test_verify_root_identity_rejects_bind_alias_of_guarded_root(tmp_path, monkeypatch) -> None:
    """Finding 1 (T5-SEC-003): a write root on the same superblock as a
    guarded root but under a different mount is a bind alias and fails."""
    from orchestrator.providers import omp_launch_policy as policy

    guarded = tmp_path / "guarded"
    guarded.mkdir()
    write_dir = tmp_path / "write-root"
    write_dir.mkdir()
    rows = [("protected", "omp-home", str(guarded)),
            ("write", "data", str(write_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (guarded, write_dir)]
    try:
        monkeypatch.setattr(
            policy, "_mount_id_for_path",
            lambda path: 11 if path == str(guarded) else 22,
        )
        with pytest.raises(policy.LaunchFsError, match="bind"):
            policy.verify_root_identity_relations(rows, fds)
    finally:
        for fd in fds:
            os.close(fd)


def test_verify_root_identity_admits_sibling_roots_on_one_mount(tmp_path) -> None:
    """Finding 1: ordinary same-superblock same-mount siblings stay admissible."""
    from orchestrator.providers import omp_launch_policy as policy

    guarded = tmp_path / "guarded"
    guarded.mkdir()
    write_dir = tmp_path / "write-root"
    write_dir.mkdir()
    rows = [("protected", "omp-home", str(guarded)),
            ("write", "data", str(write_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (guarded, write_dir)]
    try:
        policy.verify_root_identity_relations(rows, fds)  # no raise
    finally:
        for fd in fds:
            os.close(fd)


def test_verify_root_identity_admits_distinct_superblocks(tmp_path, monkeypatch) -> None:
    """Finding 1: legitimate separate-superblock roots (tmpfs, other
    partitions) skip the alias check entirely and stay admissible."""
    from orchestrator.providers import omp_launch_policy as policy

    guarded = tmp_path / "guarded"
    guarded.mkdir()
    write_dir = tmp_path / "write-root"
    write_dir.mkdir()
    rows = [("protected", "omp-home", str(guarded)),
            ("write", "data", str(write_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (guarded, write_dir)]
    try:
        monkeypatch.setattr(policy, "_fd_is_same_superblock", lambda a, b: False)
        monkeypatch.setattr(
            policy, "_mount_id_for_path",
            lambda path: (_ for _ in ()).throw(
                AssertionError("mount lookup must be skipped")
            ),
        )
        policy.verify_root_identity_relations(rows, fds)  # no raise
    finally:
        for fd in fds:
            os.close(fd)


# ---------------------------------------------------------------------------
# Task 5 review fix round 4: retained-fd statx mount ids + one-fd final
# parent acceptance (RED-first regression suite)
# ---------------------------------------------------------------------------


def test_fd_mount_id_reports_real_mount_for_retained_fd(tmp_path) -> None:
    """Finding 1 (T5-SEC-003): the retained-fd statx path yields real,
    consistent mount ids without any pathname or /proc lookup."""
    from orchestrator.providers import omp_launch_policy as policy

    first = tmp_path / "a"
    first.mkdir()
    second = tmp_path / "b"
    second.mkdir()
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (first, second)]
    try:
        ids = [policy._fd_mount_id(fd) for fd in fds]
        assert ids[0] == ids[1], "sibling dirs share one mount"
        assert isinstance(ids[0], int) and ids[0] > 0
    finally:
        for fd in fds:
            os.close(fd)


def test_verify_root_identity_rejects_bind_alias_between_write_roots(tmp_path, monkeypatch) -> None:
    """Finding 1 (T5-SEC-003): write x write pairs must also reject a
    same-superblock different-mount alias, even with equal rights masks."""
    from orchestrator.providers import omp_launch_policy as policy

    data_dir = tmp_path / "data-root"
    data_dir.mkdir()
    state_dir = tmp_path / "state-root"
    state_dir.mkdir()
    rows = [("write", "data", str(data_dir)), ("write", "state", str(state_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (data_dir, state_dir)]
    try:
        monkeypatch.setattr(
            policy, "_fd_mount_id",
            lambda fd: 11 if fd == fds[0] else 22,
        )
        with pytest.raises(policy.LaunchFsError, match="bind"):
            policy.verify_root_identity_relations(rows, fds)
    finally:
        for fd in fds:
            os.close(fd)


def test_verify_root_identity_rejects_bind_alias_of_guarded_root(tmp_path, monkeypatch) -> None:
    """Finding 1 (T5-SEC-003): a write root on the same superblock as a
    guarded root but under a different mount is a bind alias and fails."""
    from orchestrator.providers import omp_launch_policy as policy

    guarded = tmp_path / "guarded"
    guarded.mkdir()
    write_dir = tmp_path / "write-root"
    write_dir.mkdir()
    rows = [("protected", "omp-home", str(guarded)),
            ("write", "data", str(write_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (guarded, write_dir)]
    try:
        monkeypatch.setattr(
            policy, "_fd_mount_id",
            lambda fd: 11 if fd == fds[0] else 22,
        )
        with pytest.raises(policy.LaunchFsError, match="bind"):
            policy.verify_root_identity_relations(rows, fds)
    finally:
        for fd in fds:
            os.close(fd)


def test_verify_root_identity_admits_sibling_roots_on_one_mount(tmp_path) -> None:
    """Finding 1: ordinary same-superblock same-mount siblings stay admissible."""
    from orchestrator.providers import omp_launch_policy as policy

    guarded = tmp_path / "guarded"
    guarded.mkdir()
    write_dir = tmp_path / "write-root"
    write_dir.mkdir()
    rows = [("protected", "omp-home", str(guarded)),
            ("write", "data", str(write_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (guarded, write_dir)]
    try:
        policy.verify_root_identity_relations(rows, fds)  # no raise
    finally:
        for fd in fds:
            os.close(fd)


def test_verify_root_identity_admits_distinct_superblocks(tmp_path, monkeypatch) -> None:
    """Finding 1: legitimate separate-superblock roots (tmpfs, other
    partitions) skip the alias check entirely and stay admissible."""
    from orchestrator.providers import omp_launch_policy as policy

    guarded = tmp_path / "guarded"
    guarded.mkdir()
    write_dir = tmp_path / "write-root"
    write_dir.mkdir()
    rows = [("protected", "omp-home", str(guarded)),
            ("write", "data", str(write_dir))]
    fds = [os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
           for path in (guarded, write_dir)]
    try:
        monkeypatch.setattr(policy, "_fd_is_same_superblock", lambda a, b: False)
        monkeypatch.setattr(
            policy, "_fd_mount_id",
            lambda fd: (_ for _ in ()).throw(
                AssertionError("mount lookup must be skipped")
            ),
        )
        policy.verify_root_identity_relations(rows, fds)  # no raise
    finally:
        for fd in fds:
            os.close(fd)


# ---------------------------------------------------------------------------
# Task 10 remediation R5 REDs (recursive close-time observation in launch)
# ---------------------------------------------------------------------------


def _session_fixture(name: str) -> bytes:
    return (
        Path(__file__).parent / "fixtures" / "omp" / "sessions" / name
    ).read_bytes()


def _r5_preset_env(home: Path, root: Path) -> dict:
    """Profile env with a live broker pair; the conf root is the packaged
    advised-fanout preset so the canonical digest selects its topology."""
    env = _broker_env(home, root)
    return env


def _artifacts_dir(session_dir: Path, journal_name: str) -> Path:
    artifacts = session_dir / journal_name[: -len(".jsonl")]
    artifacts.mkdir(parents=True, exist_ok=True)
    return artifacts


def test_r5_fresh_launch_duplicate_direct_primary_fails(tmp_path) -> None:
    """R5: the close-time observer selects exactly one direct primary by the
    stdout session id; a second direct journal (even for another id) fails
    the adapter before any frame is written."""
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    other = "2026-08-24T00-00-00-000Z_99999999-9999-7999-8999-999999999999.jsonl"
    (session_dir / other).write_bytes(
        _session_fixture("2026-08-23T22-33-31-340Z_11111111-1111-7111-8111-111111111111.jsonl")
    )
    argv = _adapter_argv("omp_no_tools", conf_root=str(omp_launch.neutral_conf_root()),
                         session_dir=str(session_dir))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh",
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 2, (rc, err.getvalue())
    assert "more than one direct journal" in err.getvalue(), err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_r5_fresh_launch_recognized_preset_topology_and_observation(tmp_path) -> None:
    """R5: a real fresh launch through the packaged advised-fanout conf runs
    the recursive close-time observer: the planted advisor and two child
    journals satisfy the X5 predicates, the canonical digest enforces the
    counts, and the frame binds the recursive relpaths under observed while
    the primary stays under session."""
    from orchestrator.omp_assets import preset_conf_root
    from orchestrator.providers.omp_conf import admit_conf_tree

    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    artifacts = _artifacts_dir(session_dir, f"{TS_STEM}_{SESSION_ID}.jsonl")
    (artifacts / "__advisor.jsonl").write_bytes(_session_fixture("__advisor.jsonl"))
    (artifacts / "alpha.jsonl").write_bytes(_session_fixture("alpha.jsonl"))
    (artifacts / "beta.jsonl").write_bytes(_session_fixture("beta.jsonl"))
    conf_root = preset_conf_root("advised-fanout")
    argv = _adapter_argv("omp_no_tools", conf_root=str(conf_root),
                         session_dir=str(session_dir))
    prefix = f"{TS_STEM}_{SESSION_ID}.jsonl"[: -len(".jsonl")]
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh", conf_root=str(conf_root),
        observed=(f"{prefix}/alpha.jsonl", f"{prefix}/beta.jsonl"),
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, (rc, err.getvalue())
    frame = _assert_success(rc=rc, out=out, err=err, expectation=expectation)
    journal = f"{TS_STEM}_{SESSION_ID}.jsonl"
    prefix = journal[: -len(".jsonl")]
    assert frame["session"]["primary_relpath"] == journal
    assert frame["observed"] == {
        "advisor_relpaths": [f"{prefix}/__advisor.jsonl"],
        "child_relpaths": [f"{prefix}/alpha.jsonl", f"{prefix}/beta.jsonl"],
    }
    # The canonical packaged digest is the only selector for the counts.
    fd = os.open(conf_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        digest = admit_conf_tree(fd).manifest_sha256
    finally:
        os.close(fd)
    assert digest == expectation.conf_manifest_sha256


def test_r5_fresh_launch_malformed_advisor_journal_fails(tmp_path) -> None:
    """R5: a planted malformed advisor journal fails the recursive observer
    and the adapter writes no frame."""
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    artifacts = _artifacts_dir(session_dir, f"{TS_STEM}_{SESSION_ID}.jsonl")
    (artifacts / "__advisor.jsonl").write_bytes(b'{"type":"title","v":1}\nbroken\n')
    argv = _adapter_argv("omp_no_tools", conf_root=str(omp_launch.neutral_conf_root()),
                         session_dir=str(session_dir))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh",
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 2, (rc, err.getvalue())
    assert "advisor" in err.getvalue().lower(), err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def _child_journal_with_cwd(fixture: bytes, cwd: str) -> bytes:
    """Rewrite a child fixture journal's session-header cwd (line 2, after the
    256-byte title slot) so the close-time worktree predicate sees the path."""
    import json as _json

    lines = fixture.split(b"\n")
    header = _json.loads(lines[1])
    header["cwd"] = cwd
    lines[1] = _json.dumps(header, separators=(",", ":")).encode("utf-8")
    return b"\n".join(lines)


def _profile_attempt_home(env, session_dir, conf_root) -> str:
    """Re-derive the adapter-owned attempt HOME exactly like the adapter
    (same nonce as the frozen empty-cwd carrier)."""
    from orchestrator.providers.omp_launch_policy import (
        EMPTY_CWD_ENV,
        empty_omp_cwd_nonce,
        profile_attempt_key,
        profile_attempt_roots,
    )

    empty_cwd = env[EMPTY_CWD_ENV]
    nonce = empty_omp_cwd_nonce(
        empty_cwd,
        expected_key=profile_attempt_key(
            lane="no-tools", workspace=str(workspace_path),
            session_dir=str(session_dir), conf_root=str(conf_root),
            env_roots=_env_roots(env),
        ),
    )
    attempt = profile_attempt_roots(
        env_roots=_env_roots(env), lane="no-tools",
        workspace=str(workspace_path), session_dir=str(session_dir),
        conf_root=str(conf_root), nonce=nonce,
    )
    return attempt["HOME"]


def test_r5_fresh_launch_isolated_worktree_present_at_close_fails(tmp_path) -> None:
    """R5 RED: a child journal whose cwd lies under the pinned ~/.omp/wt base
    of the ACTUAL child HOME fails close-time observation while the worktree
    directory still exists; the adapter writes no frame."""
    from orchestrator.omp_assets import preset_conf_root

    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    conf_root = preset_conf_root("advised-fanout")
    argv = _adapter_argv("omp_no_tools", conf_root=str(conf_root),
                         session_dir=str(session_dir))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh", conf_root=str(conf_root),
    )
    attempt_home = _profile_attempt_home(run_env, session_dir, conf_root)
    wt_dir = os.path.join(attempt_home, ".omp", "wt", "wt-1")
    os.makedirs(wt_dir)
    artifacts = _artifacts_dir(session_dir, f"{TS_STEM}_{SESSION_ID}.jsonl")
    (artifacts / "__advisor.jsonl").write_bytes(_session_fixture("__advisor.jsonl"))
    (artifacts / "alpha.jsonl").write_bytes(
        _child_journal_with_cwd(_session_fixture("alpha.jsonl"), wt_dir)
    )
    (artifacts / "beta.jsonl").write_bytes(_session_fixture("beta.jsonl"))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 2, (rc, err.getvalue())
    assert "worktree" in err.getvalue(), err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_r5_fresh_launch_isolated_worktree_cleaned_up_passes(tmp_path) -> None:
    """R5 positive: the same tree passes close-time observation once the
    worktree directory is gone; the recursive relpaths bind in the frame."""
    from orchestrator.omp_assets import preset_conf_root

    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    conf_root = preset_conf_root("advised-fanout")
    argv = _adapter_argv("omp_no_tools", conf_root=str(conf_root),
                         session_dir=str(session_dir))
    prefix = f"{TS_STEM}_{SESSION_ID}.jsonl"[: -len(".jsonl")]
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh", conf_root=str(conf_root),
        observed=(f"{prefix}/alpha.jsonl", f"{prefix}/beta.jsonl"),
    )
    attempt_home = _profile_attempt_home(run_env, session_dir, conf_root)
    wt_dir = os.path.join(attempt_home, ".omp", "wt", "wt-1")
    artifacts = _artifacts_dir(session_dir, f"{TS_STEM}_{SESSION_ID}.jsonl")
    (artifacts / "__advisor.jsonl").write_bytes(_session_fixture("__advisor.jsonl"))
    (artifacts / "alpha.jsonl").write_bytes(
        _child_journal_with_cwd(_session_fixture("alpha.jsonl"), wt_dir)
    )
    (artifacts / "beta.jsonl").write_bytes(_session_fixture("beta.jsonl"))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, (rc, err.getvalue())
    journal = f"{TS_STEM}_{SESSION_ID}.jsonl"
    frame = _assert_success(rc=rc, out=out, err=err, expectation=expectation)
    assert frame["observed"] == {
        "advisor_relpaths": [f"{prefix}/__advisor.jsonl"],
        "child_relpaths": [f"{prefix}/alpha.jsonl", f"{prefix}/beta.jsonl"],
    }

# ---------------------------------------------------------------------------
# Task 10 remediation R1-R3 REDs (integration repairs)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------


def _path_resolver_env(tmp_path, binary: Path, *, name: str = "omp") -> tuple[Path, dict]:
    """One PATH dir containing ``name`` copied from ``binary``; returns (dir, env)."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / name).write_bytes(binary.read_bytes())
    (bindir / name).chmod(0o555)
    env = _std_env(_make_home(tmp_path), tmp_path)
    env["PATH"] = f"{bindir}:{env['PATH']}"
    return bindir, env


# -- R1: deployable binary admission -----------------------------------------


def test_r1_source_owner_admission_is_effective_user_or_root() -> None:
    from orchestrator.providers.omp_launch_fs import source_owner_admitted

    euid = os.geteuid()
    foreign = 65534 if euid != 65534 else 65533
    assert source_owner_admitted(euid) is True
    assert source_owner_admitted(0) is True
    assert source_owner_admitted(0, euid=euid) is True
    assert source_owner_admitted(euid, euid=euid) is True
    assert source_owner_admitted(foreign, euid=euid) is False
    assert source_owner_admitted(0, euid=foreign) is True


def test_r1_resolver_absent_omp_fails_before_probe(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    empty_dir = tmp_path / "empty-path"
    empty_dir.mkdir()
    env["PATH"] = str(empty_dir)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_fake_pin(), out=out, err=err,
              resolver=lambda: omp_launch.resolve_omp_binary(env))
    assert rc == 2, (rc, err.getvalue())
    assert "omp" in err.getvalue() and "PATH" in err.getvalue(), err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


def test_r1_resolver_finds_path_installed_pinned_binary_and_launches(tmp_path) -> None:
    pin = _launcher_pin()
    _bindir, env = _path_resolver_env(tmp_path, _fake_launcher())
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver=lambda: omp_launch.resolve_omp_binary(env))
    assert rc == 0, err.getvalue()
    _assert_success(rc=rc, out=out, err=err,
                    expectation=_expectation(pin, _adapter_argv("omp"), env=env))
    private = list(
        (
            Path(env["XDG_CACHE_HOME"])
            / "omp-i1"
            / "private"
            / pin.executable_sha256
        ).glob("attempt-*/omp")
    )
    assert len(private) == 1
    assert _sha256_file(private[0]) == pin.executable_sha256




def test_r1_private_copy_is_fresh_per_launch(tmp_path) -> None:
    from orchestrator.providers.omp_launch_fs import stage_private_copy

    source = tmp_path / "omp"
    source.write_bytes(_fake_launcher().read_bytes())
    source.chmod(0o500)
    pin = dataclasses.replace(
        _launcher_pin(), executable_sha256=_sha256_file(source)
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    first = stage_private_copy(str(source), pin, str(cache))
    second = stage_private_copy(str(source), pin, str(cache))
    assert first != second
    assert Path(first).is_file()
    assert Path(second).is_file()


def test_profile_attempt_precreates_xdg_app_roots(tmp_path) -> None:
    from orchestrator.providers.omp_launch_policy import (
        create_profile_attempt_authority,
        profile_attempt_roots,
    )

    roots = {
        name: str(tmp_path / name)
        for name in ("data", "state", "cache", "temp")
    }
    for path in roots.values():
        Path(path).mkdir()
    attempt = profile_attempt_roots(
        env_roots=roots, lane="no-tools", workspace=str(tmp_path),
        session_dir=None, conf_root=None, nonce="1",
    )
    authority = create_profile_attempt_authority(attempt)
    try:
        for name in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            app_root = Path(attempt[name]) / "omp"
            assert app_root.is_dir()
            assert app_root.stat().st_mode & 0o077 == 0
    finally:
        authority.close()


def test_r1_foreign_owner_source_fails_before_probe(tmp_path, monkeypatch) -> None:
    _bindir, env = _path_resolver_env(tmp_path, _fake_launcher())
    monkeypatch.setattr(os, "geteuid", lambda: 65534)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_launcher_pin(), out=out, err=err,
              resolver=lambda: omp_launch.resolve_omp_binary(env))
    assert rc == 2, (rc, err.getvalue())
    assert "owned" in err.getvalue(), err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


def test_r1_owner_writable_source_fails_before_probe(tmp_path) -> None:
    bindir, env = _path_resolver_env(tmp_path, _fake_launcher())
    (bindir / "omp").chmod(0o700)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp"),
        env=env,
        workspace=workspace_path,
        stdin=_control(),
        pin=_launcher_pin(),
        out=out,
        err=err,
        resolver=lambda: omp_launch.resolve_omp_binary(env),
    )
    assert rc == 2, (rc, err.getvalue())
    assert "writable" in err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


def test_r1_wrong_digest_on_path_fails_before_probe(tmp_path) -> None:
    _bindir, env = _path_resolver_env(tmp_path, _fake_launcher())
    pin = dataclasses.replace(_launcher_pin(), executable_sha256="0" * 64)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=pin, out=out, err=err,
              resolver=lambda: omp_launch.resolve_omp_binary(env))
    assert rc == 2, (rc, err.getvalue())
    assert "digest" in err.getvalue(), err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


def test_r1_symlinked_omp_on_path_fails_closed(tmp_path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "omp").symlink_to(_FAKE_SOURCE_ABS)
    env = _std_env(_make_home(tmp_path), tmp_path)
    env["PATH"] = str(bindir)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_fake_pin(), out=out, err=err,
              resolver=lambda: omp_launch.resolve_omp_binary(env))
    assert rc == 2, (rc, err.getvalue())
    assert "regular file" in err.getvalue(), err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


# -- R2: real broker pair and lane environments -------------------------------


def _broker_env(home: Path, root: Path, **overrides) -> dict:
    env = _std_env(home, root)
    env["OMP_AUTH_BROKER_URL"] = "http://127.0.0.1:1"
    env["OMP_AUTH_BROKER_TOKEN"] = "caller-token-must-not-leak"
    env.update(overrides)
    return env


def test_r2_profile_missing_broker_pair_refused_before_probe(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    env.pop("OMP_AUTH_BROKER_URL")
    env.pop("OMP_AUTH_BROKER_TOKEN")
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_fake_pin(), out=out, err=err)
    assert rc == 2, (rc, err.getvalue())
    assert "omp auth-broker serve" in err.getvalue(), err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


def test_r2_profile_misspelled_broker_variable_refused_before_probe(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    env.pop("OMP_AUTH_BROKER_TOKEN")
    env["OMP_AUTH_BROKER_TOKNE"] = "typo-secret"
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_fake_pin(), out=out, err=err)
    assert rc == 2, (rc, err.getvalue())
    assert "omp auth-broker serve" in err.getvalue(), err.getvalue()
    assert "FAKE_" not in err.getvalue()
    assert out.getvalue() == b""


def test_r2_profile_malformed_broker_url_refused_before_probe(tmp_path) -> None:
    home = _make_home(tmp_path)
    for bad in ("https://127.0.0.1:1", "http://localhost:1", "http://127.0.0.1",
                "http://user@127.0.0.1:1", "http://127.0.0.1:1?x=1",
                "http://127.0.0.1:1#frag", "http://127.0.0.1:0",
                "http://127.0.0.1:65536", "not-a-url", ""):
        env = _broker_env(home, tmp_path, OMP_AUTH_BROKER_URL=bad)
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
                  stdin=_control(), pin=_fake_pin(), out=out, err=err)
        assert rc == 2, (bad, rc, err.getvalue())
        assert "OMP_AUTH_BROKER_URL" in err.getvalue(), (bad, err.getvalue())
        assert "FAKE_" not in err.getvalue(), bad
        assert out.getvalue() == b"", bad
    # The token value must never appear in the refusal text.
    token = "must-never-appear-" + "x" * 12
    env = _broker_env(home, tmp_path, OMP_AUTH_BROKER_URL="http://localhost:1",
                      OMP_AUTH_BROKER_TOKEN=token)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools"), env=env, workspace=workspace_path,
              stdin=_control(), pin=_fake_pin(), out=out, err=err)
    assert rc == 2
    assert token not in err.getvalue(), err.getvalue()


def test_r2_valid_unreachable_broker_reaches_child_without_fallback(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)
    token_file = session_dir / "token.out"
    argv = _adapter_argv("omp_no_tools", conf_root=str(omp_launch.neutral_conf_root()),
                         session_dir=str(session_dir))
    expectation, run_env = _frozen_profile_expectation(
        pin, argv, lane="no-tools", env=env, session_dir=str(session_dir),
        visit_key=VISIT_KEY, persistence="fresh",
    )
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=run_env, workspace=workspace_path,
              stdin=_control(token_file=str(token_file)), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    broker = json.loads(reports["BROKER"][0])
    assert broker["url"] == "http://127.0.0.1:1"
    assert broker["token"] == "[redacted]"
    assert token_file.read_text(encoding="utf-8") == "caller-token-must-not-leak", (
        "the child must receive the operator-supplied token, never a fabricated one"
    )
    observed = tuple(sorted(entry.name for entry in session_dir.iterdir()))
    assert observed == (f"{TS_STEM}_{SESSION_ID}.jsonl", "token.out"), observed
    frame = _assert_success(rc=rc, out=out, err=err, expectation=expectation)
    # The non-journal token.out is manifest-only: the close-time observer
    # classifies only journals, so the frame carries no inventory entry.
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}


def test_r2_ambient_child_inherits_parent_environment(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    argv = _adapter_argv("omp")
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    child_env = json.loads(reports["ENV"][0])
    assert set(child_env) == set(env), "ambient children inherit the parent environment"
    assert "SECRET_CANARY" in child_env and "CALLER_CANARY" in child_env
    frame = _assert_success(rc=rc, out=out, err=err,
                            expectation=_expectation(pin, argv, env=env))
    assert frame["child"]["env_names"] == sorted(env)


def _profile_attempt(env: dict, lane: str, *, session_dir=None, conf_root=None) -> dict:
    from orchestrator.providers.omp_launch_policy import profile_attempt_roots

    if conf_root is None and lane in ("no-tools", "conf", "conf-inference"):
        conf_root = str(omp_launch.neutral_conf_root())
    return profile_attempt_roots(
        env_roots=_env_roots(env), lane=lane, workspace=str(workspace_path),
        session_dir=session_dir, conf_root=conf_root, nonce=None,
    )


def test_r2_profile_child_env_is_closed_attempt_schema(tmp_path) -> None:
    from orchestrator.providers.omp_launch_contract import (
        BROKER_TOKEN_ENV,
        BROKER_URL_ENV,
        PROFILE_ENV_NAMES,
    )

    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    attempt = _profile_attempt(env, "no-tools")
    argv = _adapter_argv("omp_no_tools", conf_root=str(omp_launch.neutral_conf_root()))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    child_env = json.loads(reports["ENV"][0])
    assert set(child_env) <= set(PROFILE_ENV_NAMES), set(child_env) - set(PROFILE_ENV_NAMES)
    required = {"HOME", "PATH", "SHELL", "PI_CODING_AGENT_DIR", "TMPDIR",
                "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME",
                "XDG_CONFIG_HOME", BROKER_URL_ENV, BROKER_TOKEN_ENV}
    assert required <= set(child_env)
    for secret in ("SECRET_CANARY", "CALLER_CANARY", "caller-token"):
        assert secret not in reports["ENV"][0] + reports["BROKER"][0]
    values = json.loads(reports["VALUES"][0])
    assert values["HOME"] == attempt["HOME"]
    assert values["PI_CODING_AGENT_DIR"] == os.path.join(attempt["HOME"], ".omp", "agent")
    assert values["SHELL"] == "/bin/bash"
    assert values["XDG_CACHE_HOME"] == attempt["XDG_CACHE_HOME"]
    assert values["XDG_DATA_HOME"] == attempt["XDG_DATA_HOME"]
    assert values["XDG_STATE_HOME"] == attempt["XDG_STATE_HOME"]
    assert values["XDG_CONFIG_HOME"] == attempt["XDG_CONFIG_HOME"]
    assert values["TMPDIR"] == attempt["TMPDIR"]
    assert values[BROKER_URL_ENV] == "http://127.0.0.1:1"
    assert values[BROKER_TOKEN_ENV] == "[redacted]"
    assert not os.path.exists(attempt["HOME"]), "attempt roots are removed at run end"
    assert not os.path.exists(os.path.dirname(attempt["HOME"])), "attempt tree removed"


def test_r2_x2_exact_child_argv_all_lanes(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()

    def _empty(lane: str, *, session_dir=None,
               conf_root=str(omp_launch.neutral_conf_root())) -> str:
        return omp_launch.empty_omp_cwd(
            home=env["HOME"], lane=lane, workspace=str(workspace_path),
            session_dir=session_dir, conf_root=conf_root,
            env_roots=_env_roots(env),
        )

    base = ["-p", "--mode", "json", "--no-title"]
    expected = {
        "omp": base + ["--model", MODEL, "--approval-mode", "write", "--no-session"],
        "omp_unrestricted_workspace": base + ["--model", MODEL, "--yolo", "--no-session"],
        "omp_no_tools": base + ["--no-extensions", "--no-skills", "--no-rules",
                                "--no-tools", "--model", MODEL, "--approval-mode",
                                "write", "--cwd", _empty("no-tools"), "--no-session"],
        "omp_conf_inference": base + ["--no-extensions", "--no-skills", "--no-rules",
                                      "--no-tools", "--model", MODEL,
                                      "--approval-mode", "write",
                                      "--cwd", _empty("conf-inference"),
                                      "--no-session"],
    }
    for lane, want in expected.items():
        argv = _adapter_argv(lane)
        if lane == "omp_no_tools":
            argv = _adapter_argv(lane, conf_root=str(omp_launch.neutral_conf_root()))
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(),
                  pin=pin, out=out, err=err, resolver_path=_fake_launcher())
        assert rc == 0, (lane, err.getvalue())
        reports = _reports(err.getvalue())
        assert json.loads(reports["ARGS"][0]) == want, lane
    # conf lane carries --add-dir; fresh carries --session-dir.
    conf_root = _make_conf(tmp_path)
    session_dir = _live_dir(tmp_path)
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root),
                         session_dir=str(session_dir))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    child_args = json.loads(reports["ARGS"][0])
    assert child_args[:-1] == base + [
        "--no-extensions", "--no-skills", "--no-rules", "--model", MODEL,
        "--approval-mode", "write", "--cwd",
        _empty("conf", session_dir=str(session_dir), conf_root=str(conf_root)),
        "--add-dir", str(workspace_path), "--session-dir",
    ]
    assert re.fullmatch(r"/proc/self/fd/[0-9]+", child_args[-1])


def test_r2_conf_materialized_at_pinned_discovery_path(tmp_path) -> None:

    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    conf = tmp_path / "discovery-conf"
    (conf / "agent" / "agents").mkdir(parents=True)
    from orchestrator.providers.omp_conf import BUNDLED_AGENT_NAMES

    (conf / "config.yml").write_text(
        "advisor:\n  enabled: false\nmemory:\n  backend: \"off\"\n"
        "task:\n  maxConcurrency: 1\n  maxRecursionDepth: 0\n"
        "  disabledAgents: [" + ", ".join(BUNDLED_AGENT_NAMES) + "]\n",
        encoding="utf-8",
    )
    (conf / "agent" / "agents" / "materialized.md").write_text(
        "---\nname: materialized\ndescription: discovery seed\n---\nbody\n",
        encoding="utf-8",
    )
    attempt = _profile_attempt(env, "no-tools", conf_root=str(conf))
    argv = _adapter_argv("omp_no_tools", conf_root=str(conf))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(),
              pin=pin, out=out, err=err, resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    assert json.loads(reports["AGENTS"][0]) == ["materialized.md"], (
        "the admitted conf must be materialized at the pinned discovery path"
    )
    assert not os.path.exists(attempt["HOME"]), "attempt roots removed at run end"


# -- R3: real profile completion wiring (fake child; real checks stay Main's) --


def test_r3_profile_fake_completion_with_broker_positives_and_negatives(
    tmp_path,
) -> None:

    home = _make_home(tmp_path)
    env = _broker_env(home, tmp_path)
    pin = _launcher_pin()
    attempt = _profile_attempt(env, "no-tools")
    argv = _adapter_argv("omp_no_tools", conf_root=str(omp_launch.neutral_conf_root()))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path,
              stdin=_control(probe=True), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    reports = _reports(err.getvalue())
    denied = [v for v in reports["PROBE"] if v.startswith(str(attempt["HOME"]) + "/.omp ")]
    assert sorted(denied) == sorted(
        f"{attempt['HOME']}/.omp {op}=denied"
        for op in ("create", "write", "truncate", "replace", "rename", "restore")
    )
    spawned = [v for v in reports["SPAWNED_PROBE"]
               if v.startswith(str(attempt["HOME"]) + "/.omp ")]
    assert sorted(spawned) == sorted(
        f"{attempt['HOME']}/.omp {op}=denied"
        for op in ("create", "write", "truncate", "replace", "rename", "restore")
    )
    for root in (attempt["XDG_DATA_HOME"], attempt["XDG_STATE_HOME"],
                 attempt["XDG_CACHE_HOME"], attempt["TMPDIR"]):
        assert sorted(v for v in reports["PROBE"] if v.startswith(root + " ")) == sorted(
            f"{root} {op}=ok" for op in ("create", "write")
        ), root
    assert not os.path.exists(attempt["HOME"]), "attempt roots removed at run end"
