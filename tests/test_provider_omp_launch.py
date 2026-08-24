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


def _make_home(root: Path) -> Path:
    agents = root / "home" / ".omp" / "agent" / "agents"
    agents.mkdir(parents=True)
    (agents / "custom.md").write_text(
        "---\nname: custom\ndescription: test agent\n---\nbody\n", encoding="utf-8"
    )
    return root / "home"


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
    pin = _fake_pin()
    argv = _adapter_argv("omp")
    stdin = _control()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=stdin, pin=pin, out=out, err=err)

    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL]
    assert reports["CWD"][0] == str(workspace_path)
    assert reports["STDIN"][0] == base64.b64encode(stdin).decode("ascii")
    assert set(json.loads(reports["ENV"][0])) == _POSITIVE_ENV_NAMES
    assert json.loads(reports["AGENTS"][0]) == ["agents"]
    broker = json.loads(reports["BROKER"][0])
    assert _BROKER_URL_RE.fullmatch(broker["url"])
    assert _HEX64_RE.fullmatch(broker["token"])
    assert broker["token"] != "caller-token-must-not-leak"
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
    private = Path(env["XDG_CACHE_HOME"]) / "omp-i1" / "private" / pin.executable_sha256 / "fake_omp.py"
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
    pin = _fake_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_unrestricted_workspace"), env=env,
              workspace=workspace_path, stdin=_control(), pin=pin, out=out, err=err)
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL, "--yolo"]
    _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, _adapter_argv("omp_unrestricted_workspace"),
                                 lane="ambient-unrestricted", env=env),
    )

    session_dir = tmp_path / "visits" / f"{VISIT_KEY}.live"
    session_dir.mkdir(parents=True)
    argv = _adapter_argv("omp", session_dir=str(session_dir))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(), pin=pin, out=out, err=err)
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
    assert os.listdir(empty_cwd) == []
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
    pin = _fake_pin()
    argv = _adapter_argv("omp_no_tools")

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err)
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL, "--no-tools"]
    empty_cwd = _profile_assertions(reports, env, home, "no-tools")

    conf_root = str(omp_launch.neutral_conf_root())
    expectation = _expectation(pin, argv, lane="no-tools", env=env, conf_root=conf_root)
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
    pin = _fake_pin()
    argv = _adapter_argv("omp_conf", conf_root=str(conf_root))

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err)
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == [
        "--no-session", "--mode=json", "--model", MODEL, "--add-dir", str(workspace_path),
    ]
    _profile_assertions(reports, env, home, "conf", workspace_add=True, conf_root=str(conf_root))
    _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, lane="conf", env=env, conf_root=str(conf_root)),
    )


def test_profile_conf_inference_and_fresh_no_tools(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _fake_pin()

    argv = _adapter_argv("omp_conf_inference")
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err)
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == ["--no-session", "--mode=json", "--model", MODEL, "--no-tools"]
    _profile_assertions(reports, env, home, "conf-inference")
    _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, lane="conf-inference", env=env,
                                 conf_root=str(omp_launch.neutral_conf_root())),
    )

    session_dir = tmp_path / "visits" / f"{VISIT_KEY}.live"
    session_dir.mkdir(parents=True)
    argv = _adapter_argv("omp_no_tools", session_dir=str(session_dir))
    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(probe=True),
              pin=pin, out=out, err=err)
    reports = _reports(err.getvalue())
    assert json.loads(reports["ARGS"][0]) == [
        "--session-dir", str(session_dir), "--mode=json", "--model", MODEL, "--no-tools",
    ]
    _profile_assertions(reports, env, home, "no-tools", session_dir=str(session_dir))
    journal = session_dir / f"{TS_STEM}_{SESSION_ID}.jsonl"
    observed = tuple(sorted(entry.name for entry in session_dir.iterdir()))
    _assert_success(
        rc=rc, out=out, err=err,
        expectation=_expectation(pin, argv, lane="no-tools", env=env,
                                 persistence="fresh", session_dir=str(session_dir),
                                 visit_key=VISIT_KEY, observed=observed),
    )


def test_planted_fd_not_inherited(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    planted = socket.socketpair()[0]
    try:
        for argv in (_adapter_argv("omp"), _adapter_argv("omp_no_tools")):
            out, err = io.BytesIO(), io.StringIO()
            rc = _run(argv=argv, env=env, workspace=workspace_path, stdin=_control(),
                      pin=_fake_pin(), out=out, err=err)
            assert rc == 0, err.getvalue()
            fds = json.loads(_reports(err.getvalue())["FDS"][0])
            assert str(planted.fileno()) not in fds
    finally:
        planted.close()


def test_no_spool_and_repeated_agent_discovery(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _fake_pin()
    session_dir = tmp_path / "visits" / f"{VISIT_KEY}.live"
    session_dir.mkdir(parents=True)

    before = {str(p) for p in tmp_path.rglob("*") if p.is_file()}
    journals = set()
    for index in range(2):
        control = _control() if index == 0 else _control(ts="2026-08-24T01:02:03.456Z")
        out, err = io.BytesIO(), io.StringIO()
        rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(session_dir)),
                  env=env, workspace=workspace_path, stdin=control, pin=pin, out=out, err=err)
        assert rc == 0, err.getvalue()
        assert json.loads(_reports(err.getvalue())["AGENTS"][0]) == ["agents"]
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
    pin = _fake_pin()

    out, err = io.BytesIO(), io.StringIO()
    result: dict[str, int] = {}

    def _blocking() -> None:
        result["rc"] = _run(argv=_adapter_argv("omp_conf", conf_root=str(conf_root)),
                            env=env, workspace=workspace_path, stdin=_control(sleep=1.5),
                            pin=pin, out=out, err=err)

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
    session_dir = tmp_path / "visits" / f"{VISIT_KEY}.live"
    session_dir.mkdir(parents=True)

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp_no_tools", session_dir=str(session_dir)),
              env=env, workspace=workspace_path,
              stdin=_control(mode="primary-mismatch", journal_id="other-id"),
              pin=_fake_pin(), out=out, err=err)
    assert rc == 2
    assert "primary" in err.getvalue().lower()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_unsettled_and_nonzero_child(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _fake_pin()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(mode="unsettled"), pin=pin, out=out, err=err)
    assert rc == 1
    assert "settle" in err.getvalue()
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=_adapter_argv("omp"), env=env, workspace=workspace_path,
              stdin=_control(exit=3), pin=pin, out=out, err=err)
    assert rc == 3
    assert b"orchestrator.omp_launch.v1" not in out.getvalue()


def test_spoofed_frame_rejected_by_accumulator(tmp_path) -> None:
    home = _make_home(tmp_path)
    env = _std_env(home, tmp_path)
    pin = _fake_pin()
    argv = _adapter_argv("omp")
    spoof = ('{"type":"orchestrator.omp_launch.v1","lane":"omp","persistence":"none",'
             '"binary":{},"child":{},"session":{},"conf":{},"confinement":null,"observed":{}}')

    out, err = io.BytesIO(), io.StringIO()
    rc = _run(argv=argv, env=env, workspace=workspace_path,
              stdin=_control(mode="spoof", spoof_line=spoof), pin=pin, out=out, err=err)
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
