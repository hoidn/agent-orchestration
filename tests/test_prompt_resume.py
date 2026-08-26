"""Task 11: `prompt resume` — closed grammar, TTY gate, and preflight REDs.

Grammar failures exit 2 before any dispatch; valid grammar requires fds 0/1/2
to be TTYs before lookup/lock/writes/child. Preflight reuses the exact Task 9
active-primary lookup and the Task 9 chain validator; every failure starts no
child and publishes no continuation record. Sibling module
``test_prompt_resume_child`` covers the PTY fake-child and postcondition half.
"""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.cli.main import main
from orchestrator.prompt_resume import (
    PromptResumeError,
    build_bridge_env,
    resume_prompt_session,
)
from orchestrator.prompt_session import (
    PromptSessionError,
    parse_session_link_bytes,
    resolve_prompt_session,
)
from orchestrator.providers.omp_launch_contract import PROFILE_ENV_NAMES
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from tests.test_prompt_session import (
    PRIMARY,
    SESSION_ID,
    _canonical,
    _journal,
    _user,
)
from tests.test_prompt_session_publication import _publish, _setup_publication

FAKE_INTERACTIVE = Path(__file__).parent / "fixtures" / "omp" / "fake_omp_interactive.py"
MODEL = "gpt-5.6-sol"


def _invoke(argv: list[str]) -> int:
    try:
        return main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)


def _fake_pin() -> object:
    digest = hashlib.sha256(FAKE_INTERACTIVE.read_bytes()).hexdigest()
    return replace(OMP_BINARY_PIN, executable_sha256=digest)


def _bridge_env(tmp_path: Path, *, marker: str | None = None) -> dict[str, str]:
    home = tmp_path / "home"
    for name in ("", "data", "state", "cache", "config", "tmp", ".omp"):
        target = home if name == "" else home / name
        target.mkdir(parents=True, exist_ok=True)
        if name == "":
            os.chmod(target, 0o700)
    env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "OMP_AUTH_BROKER_URL": "http://127.0.0.1:9999",
        "OMP_AUTH_BROKER_TOKEN": "t" * 64,
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(home / "tmp"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "XDG_STATE_HOME": str(home / "state"),
    }
    if marker is not None:
        env["TASK10_MARKER"] = marker
    return env


def _resume_setup(tmp_path: Path, *, provider: str = "omp"):
    setup = _setup_publication(tmp_path, provider=provider)
    _publish(setup)
    manager = setup[0]
    return manager, setup


def _chain(manager) -> Path:
    return manager.run_root / "provider_sessions" / "task__v1.continuations"


def _records(manager) -> list[Path]:
    chain = _chain(manager)
    if not chain.exists():
        return []
    return sorted(chain.glob("*.json"))


@pytest.fixture
def pty_fds():
    """Three TTY slave fds (one PTY) so preflight runs past the TTY gate."""
    master, slave = os.openpty()
    yield (slave, slave, slave)
    os.close(master)
    os.close(slave)


def _resume_call(
    manager,
    tmp_path: Path,
    pty_fds,
    *,
    identifier: str = "run-1",
    env: dict[str, str] | None = None,
):
    return lambda: resume_prompt_session(
        runs_root=manager.run_root.parent,
        identifier=identifier,
        in_place=False,
        pin=_fake_pin(),
        binary_resolver=lambda: str(FAKE_INTERACTIVE),
        env=env if env is not None else _bridge_env(tmp_path),
        stdin_fd=pty_fds[0],
        stdout_fd=pty_fds[1],
        stderr_fd=pty_fds[2],
        cwd=str(manager.workspace),
    )


# --- grammar -----------------------------------------------------------------


def test_resume_grammar_exit_two_for_unknown_repeated_and_extra() -> None:
    assert _invoke(["prompt", "resume"]) == 2
    assert _invoke(["prompt", "resume", "run-1", "--unknown"]) == 2
    assert _invoke(["prompt", "resume", "run-1", "extra"]) == 2
    assert _invoke(["prompt", "resume", "--in-place"]) == 2
    assert _invoke(["prompt", "resume", "run-1", "--in-place", "--in-place"]) == 2
    assert _invoke(["prompt", "resume", "run-1", "--in-place", "--fork"]) == 2


def test_resume_grammar_exit_two_when_prompt_subcommand_is_unknown() -> None:
    assert _invoke(["prompt", "resume-run", "run-1"]) == 2


# --- TTY gate ----------------------------------------------------------------


def test_resume_requires_tty_before_lookup_lock_or_child(tmp_path: Path) -> None:
    # pytest fds are not TTYs: the gate must fire before any lookup/lock/write.
    assert _invoke(["prompt", "resume", "run-1"]) == 1
    assert _invoke(["prompt", "resume", "run-1", "--in-place"]) == 1


def test_resume_pty_tty_gate_raises_before_any_filesystem_work(
    tmp_path: Path,
) -> None:
    master, slave = os.openpty()
    out_fd = os.open(os.devnull, os.O_WRONLY)
    err_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        with pytest.raises(PromptResumeError, match="prompt_resume_tty_required"):
            resume_prompt_session(
                runs_root=tmp_path / "missing-runs",
                identifier="run-1",
                in_place=False,
                pin=OMP_BINARY_PIN,
                binary_resolver=lambda: str(FAKE_INTERACTIVE),
                env=_bridge_env(tmp_path),
                stdin_fd=slave,
                stdout_fd=out_fd,
                stderr_fd=err_fd,
                cwd=str(tmp_path),
            )
    finally:
        os.close(master)
        os.close(slave)
        os.close(out_fd)
        os.close(err_fd)


# --- preflight failures start no child and publish no record ------------------


def test_resume_unknown_identifier_publishes_nothing(tmp_path, pty_fds) -> None:
    manager, _setup = _resume_setup(tmp_path)
    with pytest.raises(PromptSessionError, match="prompt_session_not_found"):
        _resume_call(manager, tmp_path, pty_fds, identifier="missing")()
    assert _records(manager) == []


def test_failed_record_tail_blocks_future_resume(tmp_path, pty_fds) -> None:
    from orchestrator.prompt_resume_record import build_record
    from orchestrator.prompt_session import ContinuationState
    from orchestrator.providers.omp_launch_contract import build_interactive_argv

    manager, _setup = _resume_setup(tmp_path)
    link_raw = (
        manager.run_root / "provider_sessions" / "task__v1.session-link.json"
    ).read_bytes()
    link = parse_session_link_bytes(link_raw)
    journal = (
        manager.run_root / "provider_sessions" / "task__v1" / PRIMARY
    ).read_bytes()
    private = os.path.join(
        manager.workspace, "cache", "omp-i1", "private",
        OMP_BINARY_PIN.executable_sha256, f"attempt-{'0' * 32}", "omp",
    )
    active = ContinuationState(
        SESSION_ID,
        PRIMARY,
        hashlib.sha256(journal).hexdigest(),
        link.document["digests"]["live_manifest_sha256"],
        False,
    )
    failed = build_record(
        link_raw=link_raw,
        records=[],
        active=active,
        mode="fork",
        child_exit_code=1,
        failure="child_failed",
        result={"session_id": None, "primary_basename": None, "journal_sha256": None},
        started_at="2026-08-23T22:33:31.340Z",
        ended_at="2026-08-23T22:33:31.340Z",
        pin=OMP_BINARY_PIN,
        interactive_argv=build_interactive_argv(
            "omp",
            "gpt-5.6-sol",
            private_binary=private,
            live_dir=str(manager.run_root / link.document["paths"]["live"]),
            mode="fork",
            source_session_id=SESSION_ID,
            workspace=link.document["workflow_workspace"],
        ),
        confinement=None,
        conf_manifest=None,
        post_manifest=None,
        env_names=sorted(PROFILE_ENV_NAMES),
    )
    chain = _chain(manager)
    chain.mkdir()
    (chain / "1.json").write_bytes(failed)
    with pytest.raises(PromptSessionError, match="prompt_session_blocked"):
        _resume_call(manager, tmp_path, pty_fds)()
    assert sorted(name.name for name in _records(manager)) == ["1.json"]


def test_resume_gapped_chain_publishes_nothing(tmp_path, pty_fds) -> None:
    manager, _setup = _resume_setup(tmp_path)
    chain = _chain(manager)
    chain.mkdir()
    (chain / "1.json").write_bytes(b"{}\n")
    (chain / "3.json").write_bytes(b"{}\n")
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        _resume_call(manager, tmp_path, pty_fds)()
    assert sorted(name.name for name in _records(manager)) == ["1.json", "3.json"]


def test_resume_live_digest_drift_publishes_nothing(tmp_path, pty_fds) -> None:
    manager, _setup = _resume_setup(tmp_path)
    live = manager.run_root / "provider_sessions" / "task__v1"
    primary = next(live.glob("*.jsonl"))
    primary.write_bytes(primary.read_bytes() + b"\n")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _resume_call(manager, tmp_path, pty_fds)()
    assert _records(manager) == []


def test_resume_scaffold_drift_publishes_nothing(tmp_path, pty_fds) -> None:
    setup = _setup_publication(tmp_path)
    _publish(setup)
    manager = setup[0]
    scaffold = setup[1]
    (scaffold / "scaffold.json").write_bytes(
        (scaffold / "scaffold.json").read_bytes() + b" "
    )
    with pytest.raises(PromptResumeError, match="prompt_resume_scaffold_invalid"):
        _resume_call(manager, tmp_path, pty_fds)()
    assert _records(manager) == []


def test_resume_binary_pin_drift_publishes_nothing(tmp_path, pty_fds) -> None:
    manager, _setup = _resume_setup(tmp_path)
    metadata_path = manager.run_root / "provider_sessions" / "task__v1.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["parser_summary"]["launch_frame"]["binary"]["sha256"] = "e" * 64
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _resume_call(manager, tmp_path, pty_fds)()
    assert _records(manager) == []


@pytest.mark.parametrize("provider", ("omp_no_tools", "omp_conf"))
def test_resume_conf_drift_publishes_nothing(tmp_path, pty_fds, provider: str) -> None:
    manager, _setup = _resume_setup(tmp_path, provider=provider)
    conf = manager.run_root / "provider_sessions" / "task__v1.conf"
    (conf / "config.yml").write_bytes(
        (conf / "config.yml").read_bytes() + b"\n"
    )
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        _resume_call(manager, tmp_path, pty_fds)()
    assert _records(manager) == []


def test_resume_missing_broker_publishes_nothing(tmp_path, pty_fds) -> None:
    manager, _setup = _resume_setup(tmp_path, provider="omp_no_tools")
    env = _bridge_env(tmp_path)
    del env["OMP_AUTH_BROKER_URL"]
    with pytest.raises(PromptResumeError, match="prompt_resume_broker_missing"):
        _resume_call(manager, tmp_path, pty_fds, env=env)()
    assert _records(manager) == []


def test_resume_lock_contention_starts_no_child_and_publishes_nothing(
    tmp_path, pty_fds
) -> None:
    import fcntl

    manager, _setup = _resume_setup(tmp_path)
    sessions = manager.run_root / "provider_sessions"
    sessions_fd = os.open(
        sessions, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        lock_fd = os.open(
            "task__v1.continuations.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=sessions_fd,
        )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            with pytest.raises(PromptResumeError, match="prompt_resume_locked"):
                _resume_call(manager, tmp_path, pty_fds)()
        finally:
            os.close(lock_fd)
    finally:
        os.close(sessions_fd)
    assert _records(manager) == []


def test_resume_lock_file_is_a_sibling_of_the_numeric_inventory(
    tmp_path,
) -> None:
    from orchestrator.prompt_session_chain import read_continuations

    manager, _setup = _resume_setup(tmp_path)
    sessions = manager.run_root / "provider_sessions"
    sessions_fd = os.open(
        sessions, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        lock_fd = os.open(
            "task__v1.continuations.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=sessions_fd,
        )
        os.close(lock_fd)
        records, _expected, _identity = read_continuations(sessions_fd, "task__v1")
        assert records == []
    finally:
        os.close(sessions_fd)
    assert "task__v1.continuations.lock" in os.listdir(sessions)
    # The lock lives beside the numeric inventory, never inside it.
    assert not (sessions / "task__v1.continuations" / "lock.json").exists()


# --- environment reconstruction -----------------------------------------------


def test_build_bridge_env_requires_current_broker_pair() -> None:
    env = {
        "HOME": "/home/x", "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin",
        "TMPDIR": "/tmp", "XDG_CACHE_HOME": "/x/cache",
        "XDG_CONFIG_HOME": "/x/config", "XDG_DATA_HOME": "/x/data",
        "XDG_STATE_HOME": "/x/state",
    }
    with pytest.raises(PromptResumeError, match="prompt_resume_broker_missing"):
        build_bridge_env(env)
    env["OMP_AUTH_BROKER_URL"] = "http://127.0.0.1:1"
    with pytest.raises(PromptResumeError, match="prompt_resume_broker_missing"):
        build_bridge_env(env)


def test_build_bridge_env_is_exactly_the_positive_schema() -> None:
    env = {
        "HOME": "/home/x", "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin",
        "TMPDIR": "/tmp", "XDG_CACHE_HOME": "/x/cache",
        "XDG_CONFIG_HOME": "/x/config", "XDG_DATA_HOME": "/x/data",
        "XDG_STATE_HOME": "/x/state",
        "OMP_AUTH_BROKER_URL": "http://127.0.0.1:1",
        "OMP_AUTH_BROKER_TOKEN": "secret-token",
        "TASK10_MARKER": "must-not-leak",
    }
    built = build_bridge_env(env)
    from orchestrator.providers.omp_launch_contract import valid_launch_env_names
    assert valid_launch_env_names("omp_no_tools", sorted(built))
    assert built["OMP_AUTH_BROKER_URL"] == "http://127.0.0.1:1"
    assert built["OMP_AUTH_BROKER_TOKEN"] == "secret-token"
    assert built["PI_CODING_AGENT_DIR"] == "/home/x/.omp/agent"
    assert "TASK10_MARKER" not in built


def test_build_bridge_env_missing_positive_name_fails() -> None:
    env = {
        "HOME": "/home/x", "LANG": "C", "PATH": "/usr/bin",
        "XDG_CACHE_HOME": "/x/cache", "XDG_CONFIG_HOME": "/x/config",
        "XDG_DATA_HOME": "/x/data", "XDG_STATE_HOME": "/x/state",
        "OMP_AUTH_BROKER_URL": "http://127.0.0.1:1",
        "OMP_AUTH_BROKER_TOKEN": "secret-token",
    }
    with pytest.raises(PromptResumeError, match="prompt_resume_env_invalid"):
        build_bridge_env(env)


# --- the published link is unchanged by preflight-only calls ------------------


def test_resume_preflight_leaves_link_and_scaffold_untouched(
    tmp_path, pty_fds
) -> None:
    manager, _setup = _resume_setup(tmp_path)
    link_path = manager.run_root / "provider_sessions" / "task__v1.session-link.json"
    before = link_path.read_bytes()
    with pytest.raises(PromptSessionError, match="prompt_session_not_found"):
        _resume_call(manager, tmp_path, pty_fds, identifier="missing")()
    assert link_path.read_bytes() == before
