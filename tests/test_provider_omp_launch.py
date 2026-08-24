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
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

import orchestrator.providers.omp_launch as omp_launch
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

_FAKE_SOURCE = Path(__file__).parent / "fixtures" / "omp" / "fake_omp.py"
_FAKE_SOURCE_ABS = str(_FAKE_SOURCE.resolve())


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        launcher.chmod(0o700)  # the adapter rejects group/other-writable sources
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
    session_dir = root / "visits" / f"{key}.live"
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
        "LD_PRELOAD": "/lib/evil.so",
        "OMP_BROKER_TOKEN": "caller-token-must-not-leak",
        "OMP_BROKER_URL": "http://caller.invalid:1",
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


def _run(*, argv, env, workspace, stdin, pin, out, err, resolver_path=_FAKE_SOURCE) -> int:
    previous = os.getcwd()
    os.chdir(workspace)
    try:
        return omp_launch.run(
            argv=argv, env=env, stdin=stdin, out=out, err=err,
            pin=pin, binary_resolver=lambda: resolver_path if os.path.isabs(str(resolver_path)) else str(Path(resolver_path).resolve()),
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
                 conf_root=None, env=None, visit_key=None, observed=(), **extra) -> OmpTransportExpectation:
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
        empty_cwd = omp_launch.empty_omp_cwd(
            home=env["HOME"], lane=lane, workspace=str(workspace_path),
            session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
        )
        kwargs["confinement_policy_sha256"] = canonical_policy_digest(
            lane=lane, home_omp=os.path.join(env["HOME"], ".omp"),
            session_dir=session_dir, conf_root=conf_root,
            workspace=str(workspace_path), empty_cwd=empty_cwd,
            env_roots=_env_roots(env),
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
    from orchestrator.providers.omp_launch_policy import EMPTY_CWD_ENV

    if conf_root is None and lane in ("no-tools", "conf", "conf-inference"):
        conf_root = str(omp_launch.neutral_conf_root())
    empty_cwd = omp_launch.empty_omp_cwd(
        home=env["HOME"], lane=lane, workspace=str(workspace_path),
        session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
    )
    omp_launch.create_empty_omp_cwd(empty_cwd)
    run_env = {**env, EMPTY_CWD_ENV: str(empty_cwd)}
    return _expectation(
        pin, argv, lane=lane, persistence=persistence, session_dir=session_dir,
        conf_root=conf_root, env=env, visit_key=visit_key, observed=observed,
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
    _fails(_adapter_argv("omp_no_tools", conf_root=str(tmp_path / "conf")), "conf-lane-only")
    _fails(["run", "--lane", "omp_conf", "--model", MODEL], "conf-root")


# ---------------------------------------------------------------------------
# Ambient lanes
# ---------------------------------------------------------------------------


def test_ambient_transient_exact_argv_stream_env_and_frame(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    argv = _adapter_argv("omp")
    token_file = tmp_path / "token.out"
    stdin = _control(token_file=str(token_file))

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=stdin, pin=pin,
              out=out, err=err, resolver_path=_fake_launcher())

    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL]
    assert reports["CWD"][0] == str(workspace_path)
    assert reports["STDIN"][0] == base64.b64encode(stdin).decode("ascii")
    assert set(json.loads(reports["ENV"][0])) == _POSITIVE_ENV_NAMES
    assert json.loads(reports["AGENTS"][0]) == ["custom.md"]
    broker = json.loads(reports["BROKER"][0])
    assert _BROKER_URL_RE.fullmatch(broker["url"])
    # The relay redacts the generated token from the child stderr, so the
    # broker report reaches us scrubbed; the token itself is observable only
    # through the fake's side channel.
    assert broker["token"] == "[redacted]"
    assert broker["agent_dir"] == str(home / ".omp" / "agent")
    generated = token_file.read_text(encoding="utf-8")
    assert _HEX64_RE.fullmatch(generated)
    assert generated != "caller-token-must-not-leak"

    frame = _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, env=env),
    )
    assert frame["type"] == "orchestrator.omp_launch.v1"
    assert frame["lane"] == "ambient"
    assert frame["persistence"] == "none"
    assert frame["child"] == {
        "argv": argv, "cwd": str(workspace_path),
        "env_names": sorted(_POSITIVE_ENV_NAMES), "exit_code": 0,
    }
    assert frame["session"] == {"id": SESSION_ID, "visit_key": None,
                                "primary_relpath": None, "primary_sha256": None}
    assert frame["conf"] == {"manifest_sha256": None}
    assert frame["confinement"] is None
    assert frame["observed"] == {"advisor_relpaths": [], "child_relpaths": []}

    # Ambient probe is unconfined: the marker write succeeds.
    assert (home / ".omp" / "version-probe-marker").read_text(encoding="utf-8") == "probe-unconfined"

    # Private digest-named copy, owner-exec, whole-file hash, source substitution.
    private = (
        Path(env["XDG_CACHE_HOME"]) / "omp-i1" / "private"
        / pin.executable_sha256 / os.path.basename(os.fspath(_fake_launcher()))
    )
    assert private.is_file()
    assert (private.stat().st_mode & 0o777) == 0o500
    assert _sha256_file(private) == pin.executable_sha256
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


def test_ambient_unrestricted_yolo_and_fresh_handoff(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_unrestricted_workspace"), env=env,
              workspace=workspace_path, stdin=_control(), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL, "--yolo"]
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
    assert json.loads(reports["ARGS"][0]) == [
        "--session-dir", str(session_dir), "--mode=json", "--model", MODEL,
    ]
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    assert journal.is_file()
    frame = _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, env=env, persistence="fresh",
                                 session_dir=str(session_dir), visit_key=VISIT_KEY,
                                 observed=(journal.name,)),
    )
    assert frame["session"] == {
        "id": SESSION_ID, "visit_key": VISIT_KEY,
        "primary_relpath": journal.name, "primary_sha256": _sha256_file(journal),
    }
    assert frame["observed"]["child_relpaths"] == [journal.name]


# ---------------------------------------------------------------------------
# Profile lanes
# ---------------------------------------------------------------------------


def _profile_assertions(reports, env, home, lane, *, session_dir=None, workspace_add=False,
                        conf_root=None):
    if conf_root is None and lane in ("no-tools", "conf-inference"):
        conf_root = omp_launch.neutral_conf_root()
    empty_cwd = omp_launch.empty_omp_cwd(
        home=env["HOME"], lane=lane, workspace=str(workspace_path),
        session_dir=session_dir, conf_root=conf_root, env_roots=_env_roots(env),
    )
    assert reports["CWD"][0] == empty_cwd
    # The adapter removes the exclusive empty cwd at run end (the confined
    # child holds it read-only, so the rmdir is deterministic).
    assert not os.path.exists(empty_cwd)
    assert set(json.loads(reports["ENV"][0])) == _POSITIVE_ENV_NAMES
    for secret in ("SECRET_CANARY", "LD_PRELOAD", "caller-token"):
        assert secret not in reports["ENV"][0] + reports["BROKER"][0]
    assert not (home / ".omp" / "version-probe-marker").exists()

    denied = [v for v in reports["PROBE"] if v.startswith(str(home / ".omp") + " ")]
    assert sorted(denied) == sorted(
        f"{home}/.omp {op}=denied"
        for op in ("create", "write", "truncate", "replace", "rename", "restore")
    )
    spawned = [v for v in reports["SPAWNED_PROBE"] if v.startswith(str(home / ".omp") + " ")]
    assert sorted(spawned) == sorted(
        f"{home}/.omp {op}=denied"
        for op in ("create", "write", "truncate", "replace", "rename", "restore")
    )
    write_roots = [env["XDG_DATA_HOME"], env["XDG_STATE_HOME"], env["XDG_CACHE_HOME"], env["TMPDIR"]]
    if session_dir is not None:
        write_roots.append(session_dir)
    if workspace_add:
        write_roots.append(str(workspace_path))
    for root in write_roots:
        assert sorted(v for v in reports["PROBE"] if v.startswith(root + " ")) == sorted(
            f"{root} {op}=ok" for op in ("create", "write")
        ), root
    return empty_cwd


def test_profile_no_tools_confined_probe_and_child(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
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
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL, "--no-tools"]
    empty_cwd = _profile_assertions(reports, env, home, "no-tools")

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
    env = _std_env(home, tmp_path)
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
    assert json.loads(reports["ARGS"][0]) == [
        "--no-session", "--mode=json", "--model", MODEL, "--add-dir", str(workspace_path),
    ]
    _profile_assertions(reports, env, home, "conf", workspace_add=True, conf_root=str(conf_root))
    _assert_success(rc=rc, out=out, err=err, expectation=expectation)


def test_profile_conf_inference_and_fresh_no_tools(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
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
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL, "--no-tools"]
    _profile_assertions(reports, env, home, "conf-inference")
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
    assert json.loads(reports["ARGS"][0]) == [
        "--session-dir", str(session_dir), "--mode=json", "--model", MODEL, "--no-tools",
    ]
    _profile_assertions(reports, env, home, "no-tools", session_dir=str(session_dir))
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    observed = tuple(sorted(entry.name for entry in session_dir.iterdir()))
    fresh_expectation = dataclasses.replace(
        fresh_expectation, observed_relpaths=observed
    )
    _assert_success(rc=rc, out=out, err=err, expectation=fresh_expectation)


def test_profile_conf_fresh_session_under_workspace_coalesces(tmp_path) -> None:
    """Ruling: fresh conf coalesces the redundant session write root.

    The canonical live-session dir sits beneath the admitted conf-workspace
    write root (runs/<id>/provider_sessions/<key>.live), so the helper must
    NOT install a separate overlapping `session` Landlock rule; the workspace
    authority already permits the journal writes. The launch still binds the
    session identity, path, visit key, and journal in the frame, and the
    journal write succeeds with no overlapping write-root pair.
    """
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    conf_root = _make_conf(tmp_path)
    pin = _launcher_pin()
    session_dir = (
        workspace_path / ".orchestrate" / "runs" / "run-1"
        / "provider_sessions" / f"{VISIT_KEY}.live"
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
    assert json.loads(reports["ARGS"][0]) == [
        "--session-dir", str(session_dir), "--mode=json", "--model", MODEL,
        "--add-dir", str(workspace_path),
    ]
    # The workspace write root covers the nested session dir: probe writes
    # succeed there, and no separate session rule exists to overlap it.
    _profile_assertions(reports, env, home, "conf", session_dir=str(session_dir),
                        workspace_add=True, conf_root=str(conf_root))
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    assert journal.is_file(), "the fresh conf journal must be written under the workspace root"
    observed = tuple(sorted(entry.name for entry in session_dir.iterdir()))
    fresh_expectation = dataclasses.replace(
        expectation, observed_relpaths=observed
    )
    frame = _assert_success(rc=rc, out=out, err=err, expectation=fresh_expectation)
    assert frame["session"] == {
        "id": SESSION_ID, "visit_key": VISIT_KEY,
        "primary_relpath": journal.name,
        "primary_sha256": _sha256_file(journal),
    }
    assert frame["confinement"] == {
        "schema_version": "omp_write_confinement.v1",
        "landlock_abi": omp_launch.landlock_abi(),
        "policy_sha256": fresh_expectation.confinement_policy_sha256,
    }


def test_planted_fd_not_inherited(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
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
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()
    session_dir = _live_dir(tmp_path)

    before = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
    journals = set()
    for index in range(2):
        control = _control() if index == 0 else _control(ts="2026-08-24T01:02:03.456Z")
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(session_dir)),
                  env=env, workspace=workspace_path, stdin=control, pin=pin,
                  out=out, err=err, resolver_path=_fake_launcher())
        assert rc == 0, err.getvalue()
        assert json.loads(_reports(err.getvalue())["AGENTS"][0]) == ["custom.md"]
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    journals = {
        str(journal),
        str(session_dir / f"2026-08-24T01-02-03-456Z_{SESSION_ID}.jsonl"),
    }
    after = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
    private_prefix = str(tmp_path / "cache" / "omp-i1" / "private")
    new_files = {p for p in (after - before) if not p.startswith(private_prefix)}
    assert new_files == journals
    assert sorted(entry.name for entry in session_dir.iterdir()) == sorted(
        Path(name).name for name in journals
    )
    assert sorted(entry.name for entry in (home / ".omp" / "agent").iterdir()) == ["agents"]
    # The fake lists $PI_CODING_AGENT_DIR/agents; only the authored custom
    # agent is visible across repeated launches (bundled/user/global absent).
    assert sorted(entry.name for entry in (home / ".omp" / "agent" / "agents").iterdir()) == ["custom.md"]


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
    _fails(Path(_FAKE_SOURCE_ABS), "digest", dataclasses.replace(pin, executable_sha256="0" * 64))


def test_version_probe_contract_and_drift(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _fake_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(), pin=dataclasses.replace(pin, version="999.0.0"),
              out=out, err=err)
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
    private = tmp_path / "private" / _fake_pin().executable_sha256 / "fake_omp.py"
    private.parent.mkdir(parents=True)
    private.parent.chmod(0o700)  # the helper requires a private current-user copy dir
    private.write_bytes(_FAKE_SOURCE.read_bytes())
    private.chmod(0o500)
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
    _fails(bad_target, "digest-named copy directory")


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_conf_runtime_mutation_fails_at_close(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
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
    env = _std_env(home, tmp_path)
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
    assert rc == 0
    _, error = _accumulate(out.getvalue(), _expectation(pin, argv, env=env))
    assert error is not None
    assert "header" in error["message"]


@pytest.mark.e2e
def test_real_pinned_binary_smoke(tmp_path) -> None:
    """Launch mechanics against the real pinned acceptance build (Task 5).

    The profile lane runs the real pinned binary confined: the version probe
    passes through the helper, the child launches with the exact positive
    environment, and its first mutation under ``$HOME/.omp`` is denied by the
    Landlock write allowlist, so the child fails at its storage initialization
    and the adapter relays the nonzero exit.
    """
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp_no_tools"),
        env=env,
        workspace=workspace_path,
        stdin=b"Reply exactly OK\n",
        pin=OMP_BINARY_PIN,
        resolver_path=omp_launch.PRODUCTION_BINARY_PATH,
        out=out,
        err=err,
    )
    text = err.getvalue()
    assert rc != 2, text
    assert "version probe" not in text
    assert "positive launch environment" not in text
    assert "child exited 1" in text, text
    assert "permission denied" in text, text


# The real pinned acceptance build needs the real auth home (agent.db with the
# stored provider credentials); both ambient smokes make one real model call.
REAL_AUTH_HOME = "/home/ollie"


@pytest.mark.e2e
def test_real_pinned_binary_ambient_transient_completes(tmp_path) -> None:
    """Real pinned binary, ambient transient lane: a real session completes
    through the adapter with the OMP JSON transport on stdout and one real
    adapter frame (lane ambient, null confinement, no session dir)."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env["HOME"] = REAL_AUTH_HOME
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp"),
        env=env,
        workspace=workspace_path,
        stdin=b"Reply with exactly: SMOKE-OK\n",
        pin=OMP_BINARY_PIN,
        resolver_path=omp_launch.PRODUCTION_BINARY_PATH,
        out=out,
        err=err,
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
def test_real_pinned_binary_ambient_fresh_completes(tmp_path) -> None:
    """Real pinned binary, ambient fresh lane: the exclusive live session dir
    receives the child-written journal; the adapter scans it and frames the
    real session id and primary journal (relpath + sha256)."""
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    env["HOME"] = REAL_AUTH_HOME
    live = tmp_path / "visits" / "v1.live"
    live.mkdir(parents=True)
    live.chmod(0o700)
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(
        argv=_adapter_argv("omp", session_dir=str(live)),
        env=env,
        workspace=workspace_path,
        stdin=b"Reply with exactly: SMOKE-OK\n",
        pin=OMP_BINARY_PIN,
        resolver_path=omp_launch.PRODUCTION_BINARY_PATH,
        out=out,
        err=err,
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
    assert primary in frame["observed"]["child_relpaths"], frame


# ---------------------------------------------------------------------------
# Task 5 review fix round: findings 1-4, 6, 7, 9 (RED-first regression suite)
# ---------------------------------------------------------------------------


def _helper_base(home: Path, env: dict, tmp_path: Path) -> tuple[list[str], Path]:
    """Helper argv with a REAL digest over the same roots the adapter uses."""
    roots = _env_roots(env)
    private = tmp_path / "private" / _fake_pin().executable_sha256 / "fake_omp.py"
    private.parent.mkdir(parents=True)
    private.parent.chmod(0o700)  # the helper requires a private current-user copy dir
    private.write_bytes(_FAKE_SOURCE.read_bytes())
    private.chmod(0o500)
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
    os.chmod(tmp_path / "private" / _fake_pin().executable_sha256, 0o777)
    _helper_fails(base, "private copy directory")


def _overlap_argv(home: Path, env: dict, tmp_path: Path, **root_mutations: str):
    """Helper argv whose digest matches a mutated write-root set."""
    roots = {**_env_roots(env), **root_mutations}
    private = tmp_path / "private" / _fake_pin().executable_sha256 / "fake_omp.py"
    private.parent.mkdir(parents=True)
    private.parent.chmod(0o700)
    private.write_bytes(_FAKE_SOURCE.read_bytes())
    private.chmod(0o500)
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
    env = _std_env(home, tmp_path)
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
    env = _std_env(home, tmp_path)
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


def test_adapter_relay_redacts_the_broker_token(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _launcher_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(leak_token=True), pin=pin, out=out, err=err,
              resolver_path=_fake_launcher())
    assert rc == 0, err.getvalue()
    text = err.getvalue()
    assert "TOKEN_LEAK [redacted]" in text, text
    assert not re.search(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", text), text


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
    private = (
        Path(env["XDG_CACHE_HOME"]) / "omp-i1" / "private"
        / pin.executable_sha256 / os.path.basename(os.fspath(_fake_launcher()))
    )

    import subprocess as _subprocess

    real_popen = _subprocess.Popen

    def _swapping_popen(args, *a, **kw):
        argv = list(args) if isinstance(args, (list, tuple)) else [args]
        if "--version" not in argv and str(private) in argv:
            # Swap the verified private copy for attacker bytes between the
            # version probe and the child spawn. The staged copy is 0o500
            # (owner r-x), so open it for writing first; a real swap must
            # happen or this test only exercises Popen OSError handling.
            private.chmod(0o700)
            private.write_bytes(evil_launcher.read_bytes())
            private.chmod(0o500)
            assert private.read_bytes() == evil_launcher.read_bytes(), (
                "the swap must actually replace the staged file"
            )
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
    private = tmp_path / "private" / _fake_pin().executable_sha256 / "fake_omp.py"
    private.parent.mkdir(parents=True)
    private.parent.chmod(0o700)
    private.write_bytes(_FAKE_SOURCE.read_bytes())
    private.chmod(0o500)
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
    private = tmp_path / "private" / _fake_pin().executable_sha256 / "fake_omp.py"
    private.parent.mkdir(parents=True)
    private.parent.chmod(0o700)
    private.write_bytes(_FAKE_SOURCE.read_bytes())
    private.chmod(0o500)
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
    env = _std_env(home, tmp_path)
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
