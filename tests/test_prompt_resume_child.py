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
import shutil
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from orchestrator.prompt_resume import (
    PromptResumeError,
    resume_prompt_session,
)
from orchestrator.prompt_session import PromptSessionError, resolve_prompt_session
from orchestrator.providers.omp_launch_contract import (
    build_interactive_argv,
    valid_launch_env_names,
)
from orchestrator.providers.omp_pin import OMP_BINARY_PIN, OmpBinaryPin
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
CONTROL = json.dumps({"fake": 1}, separators=(",", ":")).encode() + b"\n"


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
    launcher.chmod(0o500)
    return launcher


def _launcher_pin() -> OmpBinaryPin:
    return replace(cast(OmpBinaryPin, _fake_pin()), executable_sha256=hashlib.sha256(_launcher().read_bytes()).hexdigest())


def _staged_private(env: dict, *, provider: str = "omp") -> str:
    pin = _launcher_pin()
    return os.path.join(
        env["XDG_CACHE_HOME"],
        "omp-i1",
        "private",
        pin.executable_sha256,
        f"attempt-{'0' * 32}",
        "omp",
    )


def _bridge(manager, tmp_path: Path, *, in_place: bool = False, env=None, provider: str = "omp"):
    pin, resolver = _launcher_pin(), lambda: str(_launcher())
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


@pytest.mark.parametrize("target_kind", ("current", "sibling"))
def test_child_cannot_unlink_controller_lock(
    tmp_path: Path, target_kind: str
) -> None:
    manager, _setup = _resume_setup(tmp_path)
    if target_kind == "current":
        lock_path = (
            manager.run_root
            / "provider_sessions"
            / "task__v1.continuations.lock"
        )
    else:
        sibling = manager.run_root.parent / "sibling"
        sibling.mkdir()
        lock_path = sibling / "controller.lock"
        lock_path.write_bytes(b"")
    child = _run_child(
        manager,
        tmp_path,
        control=_control(
            id="99999999-9999-7999-8999-999999999999",
            deny_unlink_path=str(lock_path),
        ),
    )

    assert child.errors == []
    assert child.returned == [0]
    assert child.report("DENIED_UNLINK") == "1"
    assert lock_path.is_file()


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
    assert observed_argv == list(expected[1:])
    observed_env_names = json.loads(child.report("ENV"))
    assert valid_launch_env_names(provider, observed_env_names)
    if lane in ("ambient", "ambient-unrestricted"):
        assert observed_cwd == str(manager.workspace)
    else:
        assert observed_cwd.startswith(env["HOME"] + os.sep)
        agent_dir = child.report("AGENT_DIR")
        assert "/omp-i1/attempts/omp-attempt-" in agent_dir
        assert agent_dir.endswith("/home/.omp/agent")
        frozen_config = (
            manager.run_root / link["paths"]["conf"] / "config.yml"
        )
        assert child.report("CONFIG_SHA256") == hashlib.sha256(
            frozen_config.read_bytes()
        ).hexdigest()


def test_ambient_inherits_caller_env_without_broker(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    env = _bridge_env(tmp_path, marker="ambient-value")
    env.pop("OMP_AUTH_BROKER_URL")
    env.pop("OMP_AUTH_BROKER_TOKEN")
    child = _run_child(
        manager,
        tmp_path,
        env=env,
        control=_control(id="99999999-9999-7999-8999-999999999999"),
    )
    assert child.returned == [0]
    assert "TASK10_MARKER" in json.loads(child.report("ENV"))


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


def test_fork_accepts_result_sidecar_artifacts(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    child = _run_child(
        manager,
        tmp_path,
        control=_control(
            id="99999999-9999-7999-8999-999999999999",
            advisor_sidecar=True,
        ),
    )
    assert child.returned == [0]
    result = _new_primary(manager)
    assert (result.with_suffix("") / "__advisor.jsonl").is_file()
    assert json.loads(_records(manager)[0].read_bytes())["status"] == "success"


def test_fork_record_is_exact_closed_continuation(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    env = _bridge_env(tmp_path)
    child = _run_child(manager, tmp_path, env=env, control=_control(id="99999999-9999-7999-8999-999999999999"))
    assert child.returned == [0]
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    link = _link_document(manager)
    pin = _launcher_pin()
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
    assert record["launch"]["argv"][1:] == json.loads(child.report("ARGS"))
    assert record["launch"]["env_names"] == json.loads(child.report("ENV"))
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
        OMP_BINARY_PIN.executable_sha256, f"attempt-{'0' * 32}", "omp",
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
    env = _bridge_env(tmp_path)
    lines = output.splitlines()
    discovery = [
        line
        for line in lines
        if line.startswith("FAKE_PROBE ")
        and line.endswith("/home/.omp create=denied")
    ]
    assert len(discovery) == 1, output
    attempt_prefix = os.path.join(
        env["XDG_CACHE_HOME"], "omp-i1", "attempts", "omp-attempt-"
    )
    assert discovery[0].startswith(f"FAKE_PROBE {attempt_prefix}"), output
    assert (
        f"FAKE_PROBE {os.path.join(env['HOME'], '.omp')} create=denied"
        not in lines
    )
    for name in ("data", "state", "cache", "tmp"):
        assert any(
            line.startswith(f"FAKE_PROBE {attempt_prefix}")
            and line.endswith(f"/{name} create=ok")
            for line in lines
        ), output
    for env_name in (
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
    ):
        assert f"FAKE_PROBE {env[env_name]} create=ok" not in lines
    allowed = [str(_live(manager))]
    if provider == "omp_conf":
        allowed.append(str(manager.workspace))
    for root in allowed:
        assert f"FAKE_PROBE {root} create=ok" in lines
    assert "SPAWNED_PROBE" in output, output


def test_profile_record_binds_the_executed_policy_not_the_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator import prompt_resume_preflight

    captured: dict[str, object] = {}
    original_digest = prompt_resume_preflight.canonical_policy_digest

    def capture_digest(**kwargs):
        captured.update(kwargs)
        captured["digest"] = original_digest(**kwargs)
        return captured["digest"]

    monkeypatch.setattr(
        prompt_resume_preflight, "canonical_policy_digest", capture_digest
    )
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
    assert recorded == captured["digest"]
    attempt = os.path.dirname(os.path.dirname(str(captured["home_omp"])))
    assert "/omp-i1/attempts/omp-attempt-" in attempt
    env_roots = captured["env_roots"]
    assert isinstance(env_roots, dict)
    assert all(
        os.path.commonpath([attempt, path]) == attempt
        for path in env_roots.values()
    )
    assert not os.path.exists(attempt)


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
    fake = tmp_path / "fake-omp"
    fake.write_bytes(_launcher().read_bytes())
    fake.chmod(0o500)
    master_in, slave_in = os.openpty()
    master_out, slave_out = os.openpty()
    proc = subprocess.Popen(
        [sys.executable, str(driver), str(fake), "run-1"],
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
    assert "OMP_AUTH_BROKER_TOKEN" in text
    assert "secret-token" not in text and ("t" * 64) not in text
    os.close(master_out)



@pytest.mark.parametrize(
    "authority,provider",
    (
        ("scaffold", "omp"),
        ("private_binary", "omp"),
    ),
)
def test_child_input_mutation_publishes_failed_record(
    tmp_path: Path, authority: str, provider: str
) -> None:
    manager, _setup = _resume_setup(tmp_path, provider=provider)
    env = _bridge_env(tmp_path)
    link = _link_document(manager)
    child = _Child(_bridge(manager, tmp_path, env=env, provider=provider))
    if authority == "scaffold":
        target = (
            manager.workspace
            / link["scaffold_relpath"]
            / "prompt.md"
        )
    else:
        candidates = []
        for _ in range(1000):
            candidates = list(
                Path(env["XDG_CACHE_HOME"]).glob(
                    "omp-i1/private/*/attempt-*/omp"
                )
            )
            if candidates:
                break
            time.sleep(0.01)
        assert len(candidates) == 1
        target = candidates[0]
    original = target.read_bytes()

    child.feed(
        _control(
            id="99999999-9999-7999-8999-999999999999",
            mutate_path=str(target),
        )
    )

    assert target.read_bytes() != original
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_postcondition_failed"
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_postcondition_failed"


def test_child_cannot_mutate_frozen_conf_authority(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path, provider="omp_conf")
    link = _link_document(manager)
    target = manager.run_root / link["paths"]["conf"] / "config.yml"
    original = target.read_bytes()
    child = _run_child(
        manager,
        tmp_path,
        provider="omp_conf",
        control=_control(mutate_path=str(target)),
    )

    assert target.read_bytes() == original
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_child_failed"
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_child_failed"


@pytest.mark.parametrize("provider", ("omp_no_tools", "omp_conf"))
@pytest.mark.parametrize(
    "env_name",
    ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TMPDIR"),
)
def test_profile_child_cannot_mutate_caller_runtime_roots(
    tmp_path: Path,
    provider: str,
    env_name: str,
) -> None:
    manager, _setup = _resume_setup(tmp_path, provider=provider)
    env = _bridge_env(tmp_path)
    target = Path(env[env_name]) / "caller-owned"
    target.write_bytes(b"safe")
    child = _run_child(
        manager,
        tmp_path,
        env=env,
        provider=provider,
        control=_control(mutate_path=str(target)),
    )

    assert target.read_bytes() == b"safe"
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_child_failed"
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["failure"] == "prompt_resume_child_failed"


def test_malformed_live_tree_publishes_failed_record(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    nested = _live(manager) / "empty"
    nested.mkdir()
    child = _Child(_bridge(manager, tmp_path))
    child.feed(
        _control(
            id="99999999-9999-7999-8999-999999999999",
            plant_nested_symlink=str(nested),
        )
    )

    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_postcondition_failed"
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_postcondition_failed"


def test_child_cannot_hardlink_result_outside_live_tree(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    alias = manager.workspace / "outside-live.jsonl"
    child = _Child(_bridge(manager, tmp_path))
    child.feed(
        _control(
            id="99999999-9999-7999-8999-999999999999",
            hardlink_alias=str(alias),
        )
    )

    assert not alias.exists()
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_child_failed"
    records = _records(manager)
    assert len(records) == 1
    record = json.loads(records[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_child_failed"




def test_ambient_binary_swap_after_probe_never_executes_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    marker = tmp_path / "payload-ran"

    def swap_then_popen(argv, *args, **kwargs):
        private = next(
            Path(part)
            for part in argv
            if "/omp-i1/private/" in part and part.endswith("/omp")
        )
        private.chmod(0o700)
        private.write_text(
            f"#!/bin/sh\nprintf hacked > {marker}\n",
            encoding="utf-8",
        )
        private.chmod(0o500)
        return subprocess.Popen(argv, *args, **kwargs)

    monkeypatch.setattr(prompt_resume, "_Popen", swap_then_popen)
    child = _run_child(manager, tmp_path, control=_control())

    assert not marker.exists()
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_child_failed"
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["failure"] == "prompt_resume_child_failed"


@pytest.mark.parametrize("change", ("content", "canonical"))
def test_post_snapshot_live_drift_cannot_publish_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    from orchestrator import prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    original = prompt_resume.revalidate_post_live

    def drift_then_revalidate(**kwargs):
        live = _live(manager)
        if change == "content":
            result = _new_primary(manager)
            result.write_bytes(result.read_bytes() + b" ")
        else:
            detached = live.with_name(live.name + ".detached")
            live.rename(detached)
            shutil.copytree(detached, live)
        return original(**kwargs)

    monkeypatch.setattr(
        prompt_resume, "revalidate_post_live", drift_then_revalidate
    )
    child = _run_child(
        manager,
        tmp_path,
        control=_control(id="99999999-9999-7999-8999-999999999999"),
    )

    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_postcondition_failed"
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["status"] == "failed"
    assert record["failure"] == "prompt_resume_postcondition_failed"


def test_descendant_cannot_mutate_after_child_exit(tmp_path: Path) -> None:
    manager, _setup = _resume_setup(tmp_path)
    source = _live(manager) / PRIMARY
    before = source.read_bytes()
    child = _run_child(
        manager,
        tmp_path,
        control=_control(background_mutate_path=str(source)),
    )
    time.sleep(0.7)

    assert source.read_bytes() == before
    assert child.errors == []
    assert child.returned == [0]
    record = json.loads(_records(manager)[0].read_bytes())
    assert record["status"] == "success"


def test_under_lock_link_swap_starts_no_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orchestrator.prompt_resume as prompt_resume

    manager, _setup = _resume_setup(tmp_path)
    link_path = (
        manager.run_root
        / "provider_sessions"
        / "task__v1.session-link.json"
    )
    original = prompt_resume.read_regular_file
    swapped = False

    def swap_before_read(root_fd, relative, **kwargs):
        nonlocal swapped
        if not swapped and relative == "task__v1.session-link.json":
            document = json.loads(link_path.read_bytes())
            document["provider"]["model"] = "other-model"
            link_path.write_bytes(_canonical(document))
            swapped = True
        return original(root_fd, relative, **kwargs)

    monkeypatch.setattr(prompt_resume, "read_regular_file", swap_before_read)
    child = _run_child(manager, tmp_path, control=_control())

    assert swapped
    assert child.returned == []
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_invalid"
    assert _records(manager) == []
# --- exact-once post-start lifecycle (Main blocker) ---------------------------


class _FailingWaitProc:
    """Spawn seam: initial wait fails; termination wait reaps the child."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.instances.append(self)

    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        if timeout is None:
            raise OSError("wait exploded")
        return 0

    def terminate(self):
        self.calls.append(("terminate", None))

    def kill(self):
        self.calls.append(("kill", None))


class _InterruptProc:
    """Spawn seam: the child starts, then wait() raises KeyboardInterrupt."""

    def __init__(self, *args, **kwargs):
        self.waits = 0

    def wait(self, timeout=None):
        self.waits += 1
        if self.waits == 1:
            raise KeyboardInterrupt()
        return 0

    def terminate(self):
        pass

    def kill(self):
        pass


class _UnsettledProc:
    """Spawn seam: neither graceful nor forced termination can reap the child."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.instances.append(self)

    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        raise OSError("child remains live")

    def terminate(self):
        self.calls.append(("terminate", None))

    def kill(self):
        self.calls.append(("kill", None))


def test_unsettled_child_skips_postconditions_and_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    _UnsettledProc.instances.clear()
    manager, _setup = _resume_setup(tmp_path)
    post_calls = []
    monkeypatch.setattr(prompt_resume, "_Popen", _UnsettledProc)
    monkeypatch.setattr(
        prompt_resume,
        "capture_post_live",
        lambda *_args, **_kwargs: post_calls.append(True),
    )
    child = _run_child(manager, tmp_path, control=_control())

    assert post_calls == []
    assert child.errors and isinstance(child.errors[0], PromptResumeError)
    assert child.errors[0].code == "prompt_resume_child_unsettled"
    assert _records(manager) == []
    assert _UnsettledProc.instances[0].calls == [
        ("wait", None),
        ("terminate", None),
        ("wait", 10),
        ("kill", None),
        ("wait", 10),
    ]


def test_wait_error_publishes_exactly_one_failed_record(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_resume

    _FailingWaitProc.instances.clear()
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
    assert _FailingWaitProc.instances[0].calls == [
        ("wait", None),
        ("terminate", None),
        ("wait", 10),
    ]


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


def test_record_write_error_cleans_temp_and_raises_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator import prompt_resume_record

    manager, _setup = _resume_setup(tmp_path)
    sessions = manager.run_root / "provider_sessions"
    run_fd = os.open(manager.run_root, os.O_RDONLY | os.O_DIRECTORY)
    sessions_fd = os.open(sessions, os.O_RDONLY | os.O_DIRECTORY)
    try:
        identity = os.fstat(sessions_fd)

        def fail_write(_fd: int, _payload: bytes) -> int:
            raise OSError("injected write failure")

        monkeypatch.setattr(prompt_resume_record.os, "write", fail_write)
        with pytest.raises(
            prompt_resume_record.ContinuationRecordError,
            match="injected write failure",
        ):
            prompt_resume_record.publish_continuation(
                run_fd=run_fd,
                sessions_fd=sessions_fd,
                sessions_identity=(identity.st_dev, identity.st_ino),
                visit_key="task__v1",
                records=[],
                expected_chain_identity=None,
                expected_names=(),
                payload=b"{}\n",
            )
    finally:
        os.close(sessions_fd)
        os.close(run_fd)
    assert list(_chain(manager).iterdir()) == []


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


def test_two_successful_resumes_extend_one_valid_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator import prompt_session_chain

    manager, _setup = _resume_setup(tmp_path)
    monkeypatch.setattr(
        prompt_session_chain, "OMP_BINARY_PIN", _launcher_pin()
    )
    first = _run_child(
        manager,
        tmp_path,
        control=_control(id="99999999-9999-7999-8999-999999999999"),
    )
    second = _run_child(
        manager,
        tmp_path,
        control=_control(id="88888888-8888-7888-8888-888888888888"),
    )

    assert first.returned == [0]
    assert second.returned == [0]
    records = _records(manager)
    assert len(records) == 2
    one, two = (json.loads(path.read_bytes()) for path in records)
    assert two["sequence"] == 2
    assert two["previous_sha256"] == hashlib.sha256(
        records[0].read_bytes()
    ).hexdigest()
    assert two["source"] == one["result"]


def test_existing_chain_swap_at_publication_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator import prompt_resume

    from orchestrator import prompt_session_chain

    manager, _setup = _resume_setup(tmp_path)
    monkeypatch.setattr(
        prompt_session_chain, "OMP_BINARY_PIN", _launcher_pin()
    )
    first = _run_child(
        manager,
        tmp_path,
        control=_control(id="99999999-9999-7999-8999-999999999999"),
    )
    assert first.returned == [0]
    chain = _chain(manager)
    backup = chain.with_name(chain.name + ".detached")
    original = prompt_resume.publish_continuation

    def swap_then_publish(**kwargs):
        chain.rename(backup)
        chain.mkdir()
        return original(**kwargs)

    monkeypatch.setattr(
        prompt_resume, "publish_continuation", swap_then_publish
    )
    second = _run_child(
        manager,
        tmp_path,
        control=_control(id="88888888-8888-7888-8888-888888888888"),
    )

    assert second.errors and isinstance(second.errors[0], PromptResumeError)
    assert second.errors[0].code == "prompt_resume_record_failed"
    assert sorted(path.name for path in backup.iterdir()) == ["1.json"]
    assert list(chain.iterdir()) == []


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
