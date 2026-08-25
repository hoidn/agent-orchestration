"""Task 9 continuation journal topology and active-primary admission."""

import hashlib
import json
import os
from pathlib import Path

import pytest

from orchestrator.prompt_session import (
    PromptSessionError,
    resolve_prompt_session,
    validate_continuation_chain,
)
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_session import build_session_manifest
from orchestrator.providers.omp_launch_contract import (
    POSITIVE_ENV_NAMES,
    build_interactive_argv,
)
from tests.test_prompt_session import (
    HEX,
    PRIMARY,
    SESSION_ID,
    TS,
    _canonical,
    _entry,
    _journal,
    _link,
    _user,
    _write_index_run,
)

NEW_ID = "22222222-2222-7222-8222-222222222222"
NEW_PRIMARY = f"2026-08-23T22-34-31-340Z_{NEW_ID}.jsonl"


def _manifest(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return build_session_manifest(descriptor).manifest_sha256
    finally:
        os.close(descriptor)


def _fork_journal(*entries: dict) -> bytes:
    data = _journal(*entries, session_id=NEW_ID)
    slot, rest = data[:256], data[256:]
    header_raw, tail = rest.split(b"\n", 1)
    header = json.loads(header_raw)
    header["parentSession"] = SESSION_ID
    return slot + json.dumps(header, separators=(",", ":")).encode() + b"\n" + tail


def _write_successful_fork(runs: Path, *, child: bool) -> Path:
    link = _write_index_run(runs, "run-1")
    sessions = runs / "run-1" / "provider_sessions"
    live = sessions / "task__v1"
    if child:
        result = _fork_journal(
            _entry(
                "session_init", "i", None,
                systemPrompt="s", task="t", tools=[], agent="child",
            ),
            _user("copied prompt", entry_id="u2", parent="i"),
        )
    else:
        result = _fork_journal(_user("continued prompt"))
    (live / NEW_PRIMARY).write_bytes(result)
    link_raw = (sessions / "task__v1.session-link.json").read_bytes()
    source = (live / PRIMARY).read_bytes()
    record = {
        "schema_version": "session_continuation.v1",
        "sequence": 1,
        "previous_sha256": hashlib.sha256(link_raw).hexdigest(),
        "status": "success",
        "mode": "fork",
        "source": {
            "session_id": SESSION_ID,
            "primary_basename": PRIMARY,
            "journal_sha256": hashlib.sha256(source).hexdigest(),
        },
        "result": {
            "session_id": NEW_ID,
            "primary_basename": NEW_PRIMARY,
            "journal_sha256": hashlib.sha256(result).hexdigest(),
        },
        "started_at": TS,
        "ended_at": TS,
        "child_exit_code": 0,
        "failure": None,
        "binary": {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        },
        "conf_manifest_sha256": None,
        "launch": {
            "argv": list(
                build_interactive_argv(
                    "omp",
                    link["provider"]["model"],
                    private_binary=str(
                        runs.parent / "cache" / "omp-i1" / "private"
                        / OMP_BINARY_PIN.executable_sha256 / "omp"
                    ),
                    live_dir=str(live),
                    mode="fork",
                    source_session_id=SESSION_ID,
                    workspace=link["workflow_workspace"],
                )
            ),
            "env_names": list(POSITIVE_ENV_NAMES),
        },
        "confinement": None,
        "pre_live_manifest_sha256": link["digests"]["live_manifest_sha256"],
        "post_live_manifest_sha256": _manifest(live),
    }
    chain = sessions / "task__v1.continuations"
    chain.mkdir()
    record_path = chain / "1.json"
    record_path.write_bytes(_canonical(record))
    return record_path


def test_lookup_accepts_only_direct_primary_fork(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_successful_fork(runs, child=False)
    resolved = resolve_prompt_session(runs, "run-1")
    assert (resolved.session_id, resolved.primary_basename) == (NEW_ID, NEW_PRIMARY)


def test_lookup_rejects_agent_shaped_fork_result(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_successful_fork(runs, child=True)
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        resolve_prompt_session(runs, "run-1")


def test_continuation_requires_bound_source_digest_integer_exit_and_terminal_failure(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    link = _write_index_run(runs, "run-1", continuation={})
    chain = runs / "run-1" / "provider_sessions" / "task__v1.continuations"
    first_raw = (chain / "1.json").read_bytes()
    first = json.loads(first_raw)
    journal_sha = first["source"]["journal_sha256"]
    for child_exit in (False, "1"):
        bad = {**first, "child_exit_code": child_exit}
        with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
            validate_continuation_chain(
                _canonical(link), [_canonical(bad)],
                initial_journal_sha256=journal_sha,
                run_root=runs / "run-1",
            )
    bad_source = {
        **first,
        "source": {**first["source"], "journal_sha256": "b" * 64},
    }
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        validate_continuation_chain(
            _canonical(link), [_canonical(bad_source)],
            initial_journal_sha256=journal_sha,
            run_root=runs / "run-1",
        )
    second = {
        **first,
        "sequence": 2,
        "previous_sha256": hashlib.sha256(first_raw).hexdigest(),
    }
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        validate_continuation_chain(
            _canonical(link), [first_raw, _canonical(second)],
            initial_journal_sha256=journal_sha,
            run_root=runs / "run-1",
        )


def test_failed_tail_blocks_before_damaged_live_validation(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_index_run(runs, "run-1", continuation={})
    live = runs / "run-1" / "provider_sessions" / "task__v1"
    (live / PRIMARY).write_bytes(b"damaged")
    with pytest.raises(PromptSessionError, match="prompt_session_blocked"):
        resolve_prompt_session(runs, "run-1")


@pytest.mark.parametrize("drift", ("binary", "model", "extra-argv", "env"))
def test_continuation_rejects_unowned_launch_authority(
    tmp_path: Path, drift: str
) -> None:
    runs = tmp_path / "runs"
    record_path = _write_successful_fork(runs, child=False)
    record = json.loads(record_path.read_bytes())
    if drift == "binary":
        record["binary"]["sha256"] = "b" * 64
    elif drift == "model":
        index = record["launch"]["argv"].index("--model") + 1
        record["launch"]["argv"][index] = "other-model"
    elif drift == "extra-argv":
        record["launch"]["argv"].extend(["--extra", "value"])
    else:
        record["launch"]["env_names"].append("UNOWNED")
        record["launch"]["env_names"].sort()
    record_path.write_bytes(_canonical(record))
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        resolve_prompt_session(runs, "run-1")


def _changed_slot() -> bytes:
    value = {"type": "title", "v": 1, "title": "changed", "updatedAt": TS, "pad": ""}
    base = json.dumps(value, separators=(",", ":")) + "\n"
    value["pad"] = " " * (256 - len(base.encode()))
    slot = (json.dumps(value, separators=(",", ":")) + "\n").encode()
    assert len(slot) == 256
    return slot


def _in_place_record(
    *, link: dict, live: Path, sequence: int, previous: bytes,
    source_id: str, source_name: str, source_bytes: bytes,
    result_bytes: bytes, pre_manifest: str, post_manifest: str,
) -> bytes:
    argv = build_interactive_argv(
        "omp",
        link["provider"]["model"],
        private_binary=str(
            live.parents[3] / "cache" / "omp-i1" / "private"
            / OMP_BINARY_PIN.executable_sha256 / "omp"
        ),
        live_dir=str(live),
        mode="in_place",
        source_session_id=source_id,
        workspace=link["workflow_workspace"],
    )
    return _canonical({
        "schema_version": "session_continuation.v1",
        "sequence": sequence,
        "previous_sha256": hashlib.sha256(previous).hexdigest(),
        "status": "success",
        "mode": "in_place",
        "source": {
            "session_id": source_id,
            "primary_basename": source_name,
            "journal_sha256": hashlib.sha256(source_bytes).hexdigest(),
        },
        "result": {
            "session_id": source_id,
            "primary_basename": source_name,
            "journal_sha256": hashlib.sha256(result_bytes).hexdigest(),
        },
        "started_at": TS,
        "ended_at": TS,
        "child_exit_code": 0,
        "failure": None,
        "binary": {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        },
        "conf_manifest_sha256": None,
        "launch": {"argv": list(argv), "env_names": list(POSITIVE_ENV_NAMES)},
        "confinement": None,
        "pre_live_manifest_sha256": pre_manifest,
        "post_live_manifest_sha256": post_manifest,
    })


def test_lookup_accepts_two_in_place_turns_with_title_change(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    link = _write_index_run(runs, "run-1")
    sessions = runs / "run-1" / "provider_sessions"
    live = sessions / "task__v1"
    primary = live / PRIMARY
    initial = primary.read_bytes()
    first = _changed_slot() + _journal(
        _user("source prompt"), _user("turn one", "u2", "u")
    )[256:]
    primary.write_bytes(first)
    first_manifest = _manifest(live)
    second = _changed_slot() + _journal(
        _user("source prompt"),
        _user("turn one", "u2", "u"),
        _user("turn two", "u3", "u2"),
    )[256:]
    primary.write_bytes(second)
    second_manifest = _manifest(live)
    link_raw = (sessions / "task__v1.session-link.json").read_bytes()
    first_record = _in_place_record(
        link=link, live=live, sequence=1, previous=link_raw,
        source_id=SESSION_ID, source_name=PRIMARY, source_bytes=initial,
        result_bytes=first, pre_manifest=link["digests"]["live_manifest_sha256"],
        post_manifest=first_manifest,
    )
    second_record = _in_place_record(
        link=link, live=live, sequence=2, previous=first_record,
        source_id=SESSION_ID, source_name=PRIMARY, source_bytes=first,
        result_bytes=second, pre_manifest=first_manifest,
        post_manifest=second_manifest,
    )
    chain = sessions / "task__v1.continuations"
    chain.mkdir()
    (chain / "1.json").write_bytes(first_record)
    (chain / "2.json").write_bytes(second_record)
    assert resolve_prompt_session(runs, "run-1").journal_bytes == second


def test_lookup_accepts_fork_followed_by_in_place(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    first_path = _write_successful_fork(runs, child=False)
    sessions = runs / "run-1" / "provider_sessions"
    live = sessions / "task__v1"
    link = json.loads((sessions / "task__v1.session-link.json").read_bytes())
    primary = live / NEW_PRIMARY
    source = primary.read_bytes()
    pre_manifest = _manifest(live)
    result = source + json.dumps(
        _user("after fork", "u2", "u"), separators=(",", ":")
    ).encode() + b"\n"
    primary.write_bytes(result)
    record = _in_place_record(
        link=link, live=live, sequence=2, previous=first_path.read_bytes(),
        source_id=NEW_ID, source_name=NEW_PRIMARY, source_bytes=source,
        result_bytes=result, pre_manifest=pre_manifest,
        post_manifest=_manifest(live),
    )
    (first_path.parent / "2.json").write_bytes(record)
    assert resolve_prompt_session(runs, "run-1").journal_bytes == result


def test_lookup_rejects_failed_tail_appended_during_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator import prompt_session_lookup

    runs = tmp_path / "runs"
    first_path = _write_successful_fork(runs, child=False)
    first_raw = first_path.read_bytes()
    first = json.loads(first_raw)
    failed = {
        **first,
        "sequence": 2,
        "previous_sha256": hashlib.sha256(first_raw).hexdigest(),
        "status": "failed",
        "source": {**first["result"]},
        "result": {
            "session_id": None,
            "primary_basename": None,
            "journal_sha256": None,
        },
        "child_exit_code": 1,
        "failure": "child_failed",
        "pre_live_manifest_sha256": first["post_live_manifest_sha256"],
        "post_live_manifest_sha256": None,
    }
    original = prompt_session_lookup.read_continuations
    calls = 0

    def append_then_inventory(sessions_fd, visit_key):
        nonlocal calls
        calls += 1
        if calls == 2:
            (first_path.parent / "2.json").write_bytes(_canonical(failed))
        return original(sessions_fd, visit_key)

    monkeypatch.setattr(
        prompt_session_lookup, "read_continuations", append_then_inventory
    )
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        resolve_prompt_session(runs, "run-1")


@pytest.mark.parametrize("drift", ("directory", "record-bytes"))
def test_lookup_rejects_same_name_continuation_authority_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    from orchestrator import prompt_session_lookup

    runs = tmp_path / "runs"
    first_path = _write_successful_fork(runs, child=False)
    original_bytes = first_path.read_bytes()
    original = prompt_session_lookup.read_continuations
    calls = 0

    def swap_then_inventory(sessions_fd, visit_key):
        nonlocal calls
        calls += 1
        if calls == 2 and drift == "directory":
            old = first_path.parent.with_name(first_path.parent.name + ".old")
            first_path.parent.rename(old)
            first_path.parent.mkdir()
            (first_path.parent / "1.json").write_bytes(original_bytes)
        elif calls == 2:
            first_path.write_bytes(original_bytes + b"\n")
        return original(sessions_fd, visit_key)

    monkeypatch.setattr(
        prompt_session_lookup, "read_continuations", swap_then_inventory
    )
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        resolve_prompt_session(runs, "run-1")


def _profile_link_and_run(runs: Path) -> tuple[dict, Path, bytes]:
    """A minimal no-tools link whose confinement digest is the stale link value."""
    link = _link(
        provider={"name": "omp_no_tools", "model": "gpt-5.6-sol", "lane": "no-tools"},
        paths={
            **_link()["paths"],
            "conf": "provider_sessions/task__v1.conf",
        },
        digests={
            **_link()["digests"],
            "conf_manifest_sha256": "f" * 64,
        },
        confinement={
            "schema_version": "omp_write_confinement.v1",
            "landlock_abi": 3,
            "policy_sha256": "b" * 64,
        },
    )
    run = runs / "run-1"
    live = run / "provider_sessions" / "task__v1"
    live.mkdir(parents=True)
    source = _journal(_user("source prompt"))
    (live / PRIMARY).write_bytes(source)
    conf = run / "provider_sessions" / "task__v1.conf"
    conf.mkdir()
    (conf / "config.yml").write_text(
        "advisor:\n  enabled: false\nmemory:\n  backend: \"off\"\ntask:\n"
        "  maxConcurrency: 4\n  maxRecursionDepth: 1\n  disabledAgents: []\n",
        encoding="utf-8",
    )
    raw = _canonical(link)
    (run / "provider_sessions" / "task__v1.session-link.json").write_bytes(raw)
    return link, run, source, live


def test_profile_continuation_accepts_fresh_policy_digest_distinct_from_link(
    tmp_path: Path,
) -> None:
    """A profile continuation may install a fresh closed policy for its own
    reconstructed conf-copy/empty-cwd roots; it must not require equality to
    the link's digest (X8: same closed X2 object/schema, not same value)."""
    runs = tmp_path / "runs"
    link, run, source, live = _profile_link_and_run(runs)
    journal_sha = hashlib.sha256(source).hexdigest()
    fresh = {
        "schema_version": "omp_write_confinement.v1",
        "landlock_abi": 3,
        "policy_sha256": "d" * 64,  # executed policy differs from the link value
    }
    record = {
        "schema_version": "session_continuation.v1",
        "sequence": 1,
        "previous_sha256": hashlib.sha256(_canonical(link)).hexdigest(),
        "status": "success",
        "mode": "in_place",
        "source": {
            "session_id": SESSION_ID,
            "primary_basename": PRIMARY,
            "journal_sha256": journal_sha,
        },
        "result": {
            "session_id": SESSION_ID,
            "primary_basename": PRIMARY,
            "journal_sha256": journal_sha,
        },
        "started_at": TS,
        "ended_at": TS,
        "child_exit_code": 0,
        "failure": None,
        "binary": {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        },
        "conf_manifest_sha256": "f" * 64,
        "launch": {
            "argv": list(
                build_interactive_argv(
                    "omp_no_tools",
                    "gpt-5.6-sol",
                    private_binary=str(
                        runs.parent / "cache" / "omp-i1" / "private"
                        / OMP_BINARY_PIN.executable_sha256 / "omp"
                    ),
                    live_dir=str(live),
                    mode="in_place",
                    source_session_id=SESSION_ID,
                    workspace=link["workflow_workspace"],
                    empty_cwd=str(runs.parent / "omp-empty-1111111111111111-2222222222222222"),
                )
            ),
            "env_names": list(POSITIVE_ENV_NAMES),
        },
        "confinement": fresh,
        "pre_live_manifest_sha256": link["digests"]["live_manifest_sha256"],
        "post_live_manifest_sha256": link["digests"]["live_manifest_sha256"],
    }
    active = validate_continuation_chain(
        _canonical(link),
        [_canonical(record)],
        initial_journal_sha256=journal_sha,
        run_root=run,
    )
    assert not active.blocked
    assert active.session_id == SESSION_ID


def test_profile_continuation_rejects_malformed_or_missing_policy(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    link, run, source, live = _profile_link_and_run(runs)
    journal_sha = hashlib.sha256(source).hexdigest()
    base = {
        "schema_version": "session_continuation.v1",
        "sequence": 1,
        "previous_sha256": hashlib.sha256(_canonical(link)).hexdigest(),
        "status": "failed",
        "mode": "in_place",
        "source": {
            "session_id": SESSION_ID,
            "primary_basename": PRIMARY,
            "journal_sha256": journal_sha,
        },
        "result": {
            "session_id": None, "primary_basename": None, "journal_sha256": None,
        },
        "started_at": TS,
        "ended_at": TS,
        "child_exit_code": 1,
        "failure": "child_failed",
        "binary": {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        },
        "conf_manifest_sha256": "f" * 64,
        "launch": {
            "argv": list(
                build_interactive_argv(
                    "omp_no_tools",
                    "gpt-5.6-sol",
                    private_binary=str(
                        runs.parent / "cache" / "omp-i1" / "private"
                        / OMP_BINARY_PIN.executable_sha256 / "omp"
                    ),
                    live_dir=str(live),
                    mode="in_place",
                    source_session_id=SESSION_ID,
                    workspace=link["workflow_workspace"],
                    empty_cwd=str(runs.parent / "omp-empty-1111111111111111-2222222222222222"),
                )
            ),
            "env_names": list(POSITIVE_ENV_NAMES),
        },
        "confinement": None,  # profile lanes may never drop confinement
        "pre_live_manifest_sha256": link["digests"]["live_manifest_sha256"],
        "post_live_manifest_sha256": None,
    }
    for bad in (
        {**base, "confinement": None},
        {**base, "confinement": {"schema_version": "omp_write_confinement.v1",
                                 "landlock_abi": 2, "policy_sha256": "d" * 64}},
        {**base, "confinement": {"schema_version": "omp_write_confinement.v1",
                                 "landlock_abi": 3, "policy_sha256": "x"}},
    ):
        with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
            validate_continuation_chain(
                _canonical(link),
                [_canonical(bad)],
                initial_journal_sha256=journal_sha,
                run_root=run,
            )


def test_ambient_continuation_rejects_gained_confinement(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    link = _write_index_run(runs, "run-1", continuation={})
    chain = runs / "run-1" / "provider_sessions" / "task__v1.continuations"
    first = json.loads((chain / "1.json").read_bytes())
    journal_sha = first["source"]["journal_sha256"]
    gained = {
        **first,
        "confinement": {
            "schema_version": "omp_write_confinement.v1",
            "landlock_abi": 3,
            "policy_sha256": "d" * 64,
        },
    }
    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        validate_continuation_chain(
            _canonical(link), [_canonical(gained)],
            initial_journal_sha256=journal_sha,
            run_root=runs / "run-1",
        )
