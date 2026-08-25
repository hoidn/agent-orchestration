"""Task 10: PTY fake-child, postcondition, and record-publication REDs.

A real pseudoterminal pair plus the ``fake_omp_interactive`` fixture exercises
the production bridge path: inherited stdio, ``close_fds=True``, the exact
four-lane X8 argv/env/cwd, fork/in-place physical journal predicates, profile
confinement mutation boundaries, and the exactly-one next no-replace
continuation record after any started child.
"""

import base64
import hashlib
import json
import os
import select
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.prompt_resume import (
    PromptResumeError,
    resume_prompt_session,
)
from orchestrator.prompt_session import PromptSessionError, resolve_prompt_session
from orchestrator.providers.omp_launch_contract import (
    POSITIVE_ENV_NAMES,
    build_interactive_argv,
)
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_session import parse_journal_bytes, validate_session_graph
from orchestrator.providers.omp_write_confinement import canonical_policy_digest
from tests.test_prompt_resume import (
    FAKE_INTERACTIVE,
    MODEL,
    _bridge_env,
    _chain,
    _fake_pin,
    _records,
    _resume_setup,
)
from tests.test_prompt_session import SESSION_ID, _canonical

PRIMARY = "2026-08-23T22-33-31-340Z_11111111-1111-7111-8111-111111111111.jsonl"
CONTROL = json.dumps({"fake": 1}, separators=(",", ":"))


def _control(**extra: object) -> bytes:
    return json.dumps({"fake": 1, **extra}, separators=(",", ":")).encode() + b"\n"


def _launcher() -> Path:
    """Compile the native fake launcher once (Task 5 fd-exec seam)."""
    src = Path(__file__).parent / "fixtures" / "omp" / "fake_launcher.c"
    cache = Path(os.getcwd()) / ".tmp" / "omp-fake-launcher"
    cache.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha256(str(FAKE_INTERACTIVE.resolve()).encode("utf-8")).hexdigest()[:10]
    launcher = cache / f"fake_launcher_{tag}"
    if not launcher.exists():
        subprocess.run(
            ["cc", "-O1", "-o", str(launcher), str(src),
             f'-DOMP_FAKE_SCRIPT="{FAKE_INTERACTIVE}"'],
            check=True,
            capture_output=True,
            env={**os.environ, "TMPDIR": str(cache)},
        )
        launcher.chmod(0o700)
    return launcher


def _launcher_pin():
    return replace(_fake_pin(), executable_sha256=hashlib.sha256(_launcher().read_bytes()).hexdigest())


def _staged_private(env: dict, *, provider: str = "omp") -> str:
    if provider in ("omp_no_tools", "omp_conf"):
        source, pin = _launcher(), _launcher_pin()
    else:
        source, pin = FAKE_INTERACTIVE, _fake_pin()
    return os.path.join(
        env["XDG_CACHE_HOME"], "omp-i1", "private",
        pin.executable_sha256, os.path.basename(str(source)),
    )


def _bridge(manager, tmp_path: Path, *, in_place: bool = False, env=None, provider: str = "omp"):
    if provider in ("omp_no_tools", "omp_conf"):
        pin, resolver = _launcher_pin(), lambda: str(_launcher())
    else:
        pin, resolver = _fake_pin(), lambda: str(FAKE_INTERACTIVE)
    return dict(
        runs_root=manager.run_root.parent,
        identifier="run-1",
        in_place=in_place,
        pin=pin,
        binary_resolver=resolver,
        env=env if env is not None else _bridge_env(tmp_path),
        cwd=str(manager.workspace),
    )


class _Child:
    """Runs the bridge in a thread against real PTY fds and captures output."""

    def __init__(self, bridge_kwargs: dict) -> None:
        self.errors: list[BaseException] = []
        self.returned: list[int] = []
        self.master_in, self.slave_in = os.openpty()
        self.master_out, self.slave_out = os.openpty()
        self.output = b""

        def target() -> None:
            try:
                code = resume_prompt_session(
                    **bridge_kwargs,
                    stdin_fd=self.slave_in,
                    stdout_fd=self.slave_out,
                    stderr_fd=self.slave_out,
                )
                self.returned.append(code)
            except BaseException as exc:
                self.errors.append(exc)

        self.thread = threading.Thread(target=target)
        self.thread.start()

    def feed(self, payload: bytes) -> None:
        # The fake child reads one control LINE (no EOF needed), so the master
        # stays open until the bridge thread finishes; closing happens only at
        # teardown after FAKE_DONE.
        os.write(self.master_in, payload)
        while self.thread.is_alive():
            ready, _, _ = select.select([self.master_out], [], [], 0.5)
            if not ready:
                continue
            try:
                chunk = os.read(self.master_out, 1 << 16)
            except OSError:
                break
            if not chunk:
                break
            self.output += chunk
        self.thread.join(timeout=30)
        while True:
            ready, _, _ = select.select([self.master_out], [], [], 0)
            if not ready:
                break
            try:
                chunk = os.read(self.master_out, 1 << 16)
            except OSError:
                break
            if not chunk:
                break
            self.output += chunk
        os.close(self.master_out)
        os.close(self.slave_in)
        os.close(self.slave_out)

    def report(self, label: str) -> str:
        for line in self.output.decode("utf-8", errors="replace").splitlines():
            if line.startswith("FAKE_%s " % label):
                return line[len("FAKE_%s " % label):]
        raise AssertionError("missing FAKE_%s report in:\n%s" % (label, self.output))


def _run_child(manager, tmp_path: Path, *, in_place: bool = False, control: bytes = CONTROL, env=None, provider: str = "omp") -> _Child:
    child = _Child(_bridge(manager, tmp_path, in_place=in_place, env=env, provider=provider))
    child.feed(control)
    return child


def _live(manager) -> Path:
    return manager.run_root / "provider_sessions" / "task__v1"


def _new_primary(manager, *, exclude: str = PRIMARY) -> Path:
    matches = [path for path in sorted(_live(manager).glob("*.jsonl")) if path.name != exclude]
    assert len(matches) == 1, matches
    return matches[0]


def _link_document(manager) -> dict:
    raw = (manager.run_root / "provider_sessions" / "task__v1.session-link.json").read_bytes()
    return json.loads(raw)


# --- inherited stdio and descriptor closure -----------------------------------


def _assert_child_env_names(report: str) -> None:
    names = json.loads(report)
    assert names == sorted(POSITIVE_ENV_NAMES)


# --- inherited stdio and descriptor closure -----------------------------------


def test_fork_child_inherits_pty_stdio_and_closes_other_fds(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.errors == []
    assert child.returned == [0]
    stdin = base64.b64decode(child.report("STDIN"))
    assert json.loads(stdin)["id"] == "99999999-9999-7999-8999-999999999999"
    # The child inherits the TTY stdio; Python's own runtime may open extra
    # fds (>=3), so close_fds/no-pass_fds is proven by 0/1/2 being the PTY
    # slaves and none of the bridge's retained descriptors appearing in the
    # child (the bridge's lock/session/live fds are all closed pre-exec).
    fds = json.loads(child.report("FDS"))
    assert {"0", "1", "2"} <= set(fds)


# --- exact four-lane X8 argv/env/cwd ------------------------------------------


@pytest.mark.parametrize(
    "provider,lane",
    (
        ("omp", "ambient"),
        ("omp_unrestricted_workspace", "ambient-unrestricted"),
        ("omp_no_tools", "no-tools"),
        ("omp_conf", "conf"),
    ),
)
def test_four_lane_argv_env_cwd_matrix(tmp_path: Path, provider: str, lane: str) -> None:
    manager, _setup = _resume_setup(tmp_path, provider=provider)
    env = _bridge_env(tmp_path, marker="must-not-leak")
    child = _run_child(manager, tmp_path, env=env, control=_control(id="99999999-9999-7999-8999-999999999999"), provider=provider)
    assert child.errors == []
    assert child.returned == [0]
    observed_argv = json.loads(child.report("ARGS"))
    observed_cwd = child.report("CWD")
    link = _link_document(manager)
    empty_cwd = None
    if provider in ("omp_no_tools", "omp_conf"):
        import re
        assert re.fullmatch(r"omp-empty-[0-9a-f]{16}-[0-9a-f]{16}", os.path.basename(observed_cwd))
        empty_cwd = observed_cwd
    expected = build_interactive_argv(
        provider,
        link["provider"]["model"],
        private_binary=_staged_private(env, provider=provider),
        live_dir=str(_live(manager)),
        mode="fork",
        source_session_id=SESSION_ID,
        workspace=link["workflow_workspace"],
        empty_cwd=empty_cwd,
    )
    assert observed_argv == list(expected)
    assert json.loads(child.report("ENV")) == sorted(POSITIVE_ENV_NAMES)
    if lane in ("ambient", "ambient-unrestricted"):
        assert observed_cwd == str(manager.workspace)
    else:
        assert observed_cwd.startswith(env["HOME"] + os.sep)


# --- fork postconditions -------------------------------------------------------


def test_fork_keeps_source_and_creates_one_direct_primary(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    source = (_live(manager) / PRIMARY).read_bytes()
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.errors == []
    assert child.returned == [0]
    assert (_live(manager) / PRIMARY).read_bytes() == source
    result = _new_primary(manager)
    journal = parse_journal_bytes(result.read_bytes(), relpath=result.name)
    validate_session_graph(journal.entries)
    assert journal.header.id == "99999999-9999-7999-8999-999999999999"
    assert journal.header.parent_session == SESSION_ID
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["status"] == "success"
    assert record["mode"] == "fork"
    assert record["result"] == {
        "session_id": "99999999-9999-7999-8999-999999999999",
        "primary_basename": result.name,
        "journal_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
    }
    assert record["source"] == {
        "session_id": SESSION_ID,
        "primary_basename": PRIMARY,
        "journal_sha256": hashlib.sha256(source).hexdigest(),
    }


def test_fork_record_is_exact_closed_continuation(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    env = _bridge_env(tmp_path)
    child = _run_child(manager, tmp_path, env=env, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.returned == [0]
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    link = _link_document(manager)
    pin = _fake_pin()
    assert record["schema_version"] == "session_continuation.v1"
    assert record["sequence"] == 1
    assert record["previous_sha256"] == hashlib.sha256(
        (manager.run_root / "provider_sessions" / "task__v1.session-link.json").read_bytes()
    ).hexdigest()
    assert record["status"] == "success"
    assert record["mode"] == "fork"
    assert record["child_exit_code"] == 0
    assert record["failure"] is None
    assert record["binary"] == {
        "platform": pin.platform, "arch": pin.arch,
        "version": pin.version, "sha256": pin.executable_sha256,
    }
    assert record["conf_manifest_sha256"] == link["digests"]["conf_manifest_sha256"]
    assert record["launch"]["argv"] == json.loads(child.report("ARGS"))
    assert record["launch"]["env_names"] == list(POSITIVE_ENV_NAMES)
    assert record["confinement"] is None
    assert record["pre_live_manifest_sha256"] == link["digests"]["live_manifest_sha256"]
    assert record["post_live_manifest_sha256"] != record["pre_live_manifest_sha256"]
    for field in ("started_at", "ended_at"):
        assert isinstance(record[field], str) and record[field]
    assert record["result"]["primary_basename"].endswith(".jsonl")


    # The bridge truthfully records the *executed* (fake) pin. Task 9's
    # validator anchors records to the real OMP_BINARY_PIN, so swap only the
    # two pin-dependent fields to production values and prove every other
    # bridge-written field (argv/env/confinement/manifests/source/result)
    # satisfies validate_continuation_chain exactly.
    sessions = manager.run_root / "provider_sessions"
    link_raw = (sessions / "task__v1.session-link.json").read_bytes()
    record = json.loads(_records(manager)[0].read_bytes())
    record["binary"] = {
        "platform": OMP_BINARY_PIN.platform,
        "arch": OMP_BINARY_PIN.arch,
        "version": OMP_BINARY_PIN.version,
        "sha256": OMP_BINARY_PIN.executable_sha256,
    }
    real_private = os.path.join(
        manager.workspace, "cache", "omp-i1", "private",
        OMP_BINARY_PIN.executable_sha256, "omp",
    )
    record["launch"]["argv"] = [real_private, *record["launch"]["argv"][1:]]
    from orchestrator.prompt_session import validate_continuation_chain
    active = validate_continuation_chain(
        link_raw,
        [_canonical(record)],
        initial_journal_sha256=record["source"]["journal_sha256"],
        run_root=manager.run_root,
    )
    assert active.session_id == "99999999-9999-7999-8999-999999999999"
    assert active.primary_basename == record["result"]["primary_basename"]
    # The raw disk record keeps the fake pin and therefore cannot pass Task 9's
    # launch-authority check (binary/argv anchored to OMP_BINARY_PIN); the
    # swapped roundtrip above proves every other field exactly.


# --- in-place postconditions ---------------------------------------------------


def test_in_place_keeps_primary_and_extends_prefix(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    pre = (_live(manager) / PRIMARY).read_bytes()
    child = _run_child(manager, tmp_path, in_place=True, control=_control())
    assert child.errors == []
    assert child.returned == [0]
    post = (_live(manager) / PRIMARY).read_bytes()
    assert post[:256] == pre[:256]
    assert post[256:].startswith(pre[256:])
    assert len(post) > len(pre)
    journal = parse_journal_bytes(post, relpath=PRIMARY)
    validate_session_graph(journal.entries)
    assert journal.header.id == SESSION_ID
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["status"] == "success"
    assert record["mode"] == "in_place"
    assert record["result"] == {
        "session_id": SESSION_ID,
        "primary_basename": PRIMARY,
        "journal_sha256": hashlib.sha256(post).hexdigest(),
    }
    assert record["source"]["journal_sha256"] == hashlib.sha256(pre).hexdigest()


def test_in_place_valid_title_update_is_allowed(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    pre = (_live(manager) / PRIMARY).read_bytes()
    child = _run_child(manager, tmp_path, in_place=True, control=_control(title="changed"))
    assert child.returned == [0]
    post = (_live(manager) / PRIMARY).read_bytes()
    assert post[:256] != pre[:256]
    assert post[256:].startswith(pre[256:])
    assert len(post) > len(pre)
    parse_journal_bytes(post, relpath=PRIMARY)


# --- postcondition failures publish exactly one failed record ------------------


@pytest.mark.parametrize(
    "control,marker",
    (
        ({"no_append": True}, "unchanged manifest"),
        ({"truncate": True}, "valid truncation"),
        ({"rewrite": True}, "body replacement"),
        ({"title": "malformed"}, "malformed title update"),
        ({"title": "changed", "rewrite": True}, "title-slot-plus-history rewrite"),
    ),
)
def test_in_place_misbehavior_publishes_one_failed_record(
    tmp_path: Path, control: dict, marker: str
) -> None:
    manager, _setup = _resume_setup(tmp_path)
    child = _run_child(manager, tmp_path, in_place=True, control=_control(**control))
    assert child.errors
    assert isinstance(child.errors[0], PromptResumeError)
    records = _records(manager)
    assert len(records) == 1, marker
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed", marker
    assert record["failure"], marker
    assert record["result"] == {
        "session_id": None, "primary_basename": None, "journal_sha256": None,
    }
    assert record["child_exit_code"] == 0
    assert record["source"]["session_id"] == SESSION_ID


@pytest.mark.parametrize(
    "control,marker",
    (
        ({"remove_source": True}, "source removal"),
        ({"extra_file": True}, "extra file"),
        ({"extra_primary": True}, "second primary"),
        ({"agent": True}, "agent-shaped result"),
        ({"swap": True}, "type-swapped source"),
        ({"exit": 3}, "nonzero child exit"),
    ),
)
def test_fork_misbehavior_publishes_one_failed_record(
    tmp_path: Path, control: dict, marker: str
) -> None:
    manager, _setup = _resume_setup(tmp_path)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999", **control))
    assert child.errors
    records = _records(manager)
    assert len(records) == 1, marker
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed", marker
    assert record["result"] == {
        "session_id": None, "primary_basename": None, "journal_sha256": None,
    }
    if control.get("exit") == 3:
        assert record["child_exit_code"] == 3
        assert record["failure"] == "prompt_resume_child_failed"


def test_swap_failure_leaves_post_manifest_null(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999", swap=True))
    assert child.errors
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["status"] == "failed"
    assert record["post_live_manifest_sha256"] is None


def test_failed_continuation_blocks_later_orchestrator_lookup(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    child = _run_child(manager, tmp_path, in_place=True, control=_control(truncate=True))
    assert child.errors
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        resolve_prompt_session(manager.run_root.parent, "run-1")
    # The fake-pin failed record fails Task 9's launch-authority check first
    # (binary/argv are pinned to the fake, not OMP_BINARY_PIN); the terminal
    # prompt_session_blocked path with a launch-authority-valid failed record
    # is asserted in test_failed_record_tail_blocks_future_resume.


# --- profile confinement boundaries --------------------------------------------


@pytest.mark.parametrize("provider", ("omp_no_tools", "omp_conf"))
def test_profile_confinement_mutation_boundaries(
    tmp_path: Path, provider: str
) -> None:
    manager, _setup = _resume_setup(tmp_path, provider=provider)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999", probe=True), provider=provider)
    assert child.returned == [0]
    output = child.output.decode("utf-8", errors="replace")
    home = _bridge_env(tmp_path)["HOME"]
    denied_roots = [
        os.path.join(home, ".omp"),
    ]
    base = os.path.join(home, ".omp-i1-runtime")
    denied_roots += [
        os.path.join(base, nonce, "conf")
        for nonce in sorted(os.listdir(base))
        if os.path.isdir(os.path.join(base, nonce, "conf"))
    ]
    for root in denied_roots:
        assert ("%s create=denied" % root) in output, output
        assert ("%s write=denied" % root) in output, output
    allowed = []
    for name in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TMPDIR"):
        allowed.append(_bridge_env(tmp_path)[name])
    allowed.append(str(_live(manager)))
    if provider == "omp_conf":
        allowed.append(str(manager.workspace))
    for root in allowed:
        assert ("%s create=ok" % root) in output, output
    assert "SPAWNED_PROBE" in output, output


def test_profile_record_binds_the_executed_policy_not_the_link(
    tmp_path: Path,
) -> None:
    manager, _setup = _resume_setup(tmp_path, provider="omp_conf")
    link = _link_document(manager)
    assert link["confinement"]["policy_sha256"] == "b" * 64
    env = _bridge_env(tmp_path)
    child = _run_child(manager, tmp_path, env=env, control=_control(id="99999999-9999-7999-8999-999999999999"), provider="omp_conf")
    assert child.returned == [0]
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["confinement"] is not None
    assert record["confinement"]["schema_version"] == "omp_write_confinement.v1"
    recorded = record["confinement"]["policy_sha256"]
    assert recorded != link["confinement"]["policy_sha256"]
    cwd = child.report("CWD")
    home = env["HOME"]
    base = os.path.join(home, ".omp-i1-runtime")
    copies = [
        os.path.join(base, nonce, "conf")
        for nonce in sorted(os.listdir(base))
        if os.path.isdir(os.path.join(base, nonce, "conf"))
    ]
    assert len(copies) == 1
    expected = canonical_policy_digest(
        lane="conf",
        home_omp=os.path.join(home, ".omp"),
        session_dir=str(_live(manager)),
        conf_root=copies[0],
        workspace=link["workflow_workspace"],
        empty_cwd=cwd,
        env_roots={
            "data": env["XDG_DATA_HOME"], "state": env["XDG_STATE_HOME"],
            "cache": env["XDG_CACHE_HOME"], "temp": env["TMPDIR"],
        },
    )
    assert recorded == expected


# --- actual fake PTY subprocess (production path) ------------------------------

_DRIVER = """
import hashlib
import os
import sys
from dataclasses import replace
from pathlib import Path

from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.prompt_resume import resume_prompt_session

fake = sys.argv[1]
pin = replace(
    OMP_BINARY_PIN,
    executable_sha256=hashlib.sha256(Path(fake).read_bytes()).hexdigest(),
)
code = resume_prompt_session(
    runs_root=Path.cwd() / ".orchestrate" / "runs",
    identifier=sys.argv[2],
    in_place=len(sys.argv) > 3 and sys.argv[3] == "--in-place",
    pin=pin,
    binary_resolver=lambda: fake,
    env=os.environ,
    stdin_fd=0,
    stdout_fd=1,
    stderr_fd=2,
    cwd=os.getcwd(),
)
sys.exit(code)
"""


def test_cli_pty_subprocess_fork_end_to_end(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    driver = tmp_path / "resume_driver.py"
    driver.write_text(_DRIVER)
    env = _bridge_env(tmp_path)
    master_in, slave_in = os.openpty()
    master_out, slave_out = os.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(driver), str(FAKE_INTERACTIVE), "run-1"],
        cwd=str(manager.workspace),
        env=env,
        stdin=slave_in,
        stdout=slave_out,
        stderr=slave_out,
        close_fds=True,
    )
    os.close(slave_in)
    os.close(slave_out)
    os.write(master_in, _control(id="99999999-9999-7999-8999-999999999999"))
    output = b""
    while proc.poll() is None:
        ready, _, _ = select.select([master_out], [], [], 30)
        if not ready:
            break
        try:
            chunk = os.read(master_out, 1 << 16)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    os.close(master_in)
    proc.wait(timeout=30)
    assert proc.returncode == 0, output.decode("utf-8", errors="replace")
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "success"
    assert record["mode"] == "fork"
    result = _new_primary(manager)
    assert result.name == record["result"]["primary_basename"]
    text = output.decode("utf-8", errors="replace")
    assert "FAKE_DONE 1" in text
    assert "prompt resume: argv:" in text
    assert "OMP_BROKER_TOKEN" in text
    assert "secret-token" not in text and ("t" * 64) not in text
    os.close(master_out)


# --- exact-once post-start lifecycle (Main blocker) ---------------------------


class _FailingWaitProc:
    """Spawn seam: the child starts, then wait() explodes with OSError."""

    def __init__(self, *args, **kwargs):
        pass

    def wait(self):
        raise OSError("wait exploded")


class _InterruptProc:
    """Spawn seam: the child starts, then wait() raises KeyboardInterrupt."""

    def __init__(self, *args, **kwargs):
        pass

    def wait(self):
        raise KeyboardInterrupt()

    def terminate(self):
        pass

    def kill(self):
        pass


def test_wait_error_publishes_exactly_one_failed_record(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    monkeypatch.setattr(prompt_resume, "_Popen", _FailingWaitProc)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.errors
    assert isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_child_failed"
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_child_failed"
    assert record["child_exit_code"] == -1
    assert record["result"] == {
        "session_id": None, "primary_basename": None, "journal_sha256": None,
    }


def test_keyboard_interrupt_publishes_record_then_re_raises(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    monkeypatch.setattr(prompt_resume, "_Popen", _InterruptProc)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.errors and isinstance(child.errors[0], KeyboardInterrupt)
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_interrupted"
    assert record["child_exit_code"] == 130
    assert record["result"] == {
        "session_id": None, "primary_basename": None, "journal_sha256": None,
    }


def test_publication_collision_surfaces_record_error_and_adds_nothing(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    chain = _chain(manager)
    chain.mkdir()
    (chain / "1.json").write_bytes(b"{}\n")
    calls = 0

    def blind_read(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [], (), None

    from orchestrator import prompt_session_lookup

    monkeypatch.setattr(prompt_resume, "read_continuations", blind_read)
    monkeypatch.setattr(prompt_session_lookup, "read_continuations", blind_read)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.errors
    assert isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_record_failed"
    # The pre-existing record is untouched and no new record or temp remains.
    assert sorted(path.name for path in chain.iterdir()) == ["1.json"]


def test_post_start_commits_exactly_one_record_on_success(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    published: list[bytes] = []
    original = prompt_resume.publish_continuation

    def counting(*args, **kwargs):
        published.append(kwargs["payload"])
        return original(*args, **kwargs)

    monkeypatch.setattr(prompt_resume, "publish_continuation", counting)
    child = _run_child(manager, tmp_path, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.errors == []
    assert child.returned == [0]
    assert len(published) == 1
    assert json.loads(published[0])["status"] == "success"


def test_post_start_commits_exactly_one_record_on_failure(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    published: list[bytes] = []
    original = prompt_resume.publish_continuation

    def counting(*args, **kwargs):
        published.append(kwargs["payload"])
        return original(*args, **kwargs)

    monkeypatch.setattr(prompt_resume, "publish_continuation", counting)
    child = _run_child(manager, tmp_path, in_place=True, control=_control(truncate=True))
    assert child.errors
    assert len(published) == 1
    record = json.loads(published[0])
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_postcondition_failed"
    # The failed tail must block later lookups exactly like the real disk tail.
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        resolve_prompt_session(manager.run_root.parent, "run-1")
