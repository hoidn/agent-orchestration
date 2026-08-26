"""Task 9: closed OMP session links, exact lookup, and prompt import."""

import hashlib
import json
import os
from pathlib import Path
import pytest

from orchestrator.prompt_session import (
    PromptSessionError,
    extract_prompt_bytes,
    parse_session_link_bytes,
    publish_prompt_run_link,
    resolve_prompt_session,
    validate_continuation_chain,
    with_private_execution_authority,
)
from orchestrator.providers.omp_session import parse_journal_bytes

TS = "2026-08-23T22:33:31.340Z"
HEX = "a" * 64
SESSION_ID = "11111111-1111-7111-8111-111111111111"
PRIMARY = f"2026-08-23T22-33-31-340Z_{SESSION_ID}.jsonl"


def _slot() -> str:
    obj = {"type": "title", "v": 1, "title": "", "updatedAt": TS, "pad": ""}
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = " " * (256 - len(base.encode()))
    result = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(result.encode()) == 256
    return result


def _entry(kind: str, entry_id: str, parent: str | None, **extra: object) -> dict:
    return {"type": kind, "id": entry_id, "parentId": parent, "timestamp": TS, **extra}


def _user(content: object, entry_id: str = "u", parent: str | None = None) -> dict:
    return _entry(
        "message", entry_id, parent,
        message={"role": "user", "content": content, "timestamp": 1},
    )


def _settled_assistant() -> dict:
    """A settled assistant turn: last closed message stops with no tool call,
    so close-time observation classifies the journal as settled."""
    return _entry(
        "message", "a", "u",
        message={
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "api": "a", "provider": "p", "model": "m",
            "stopReason": "stop", "timestamp": 2,
            "usage": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0,
                      "totalTokens": 0,
                      "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0,
                               "cacheWrite": 0.0, "total": 0.0}},
        },
    )


def _assistant(entry_id: str = "a", parent: str | None = "u") -> dict:
    usage = {
        "input": 1,
        "output": 1,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 2,
        "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0},
    }
    return _entry(
        "message",
        entry_id,
        parent,
        message={
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
            "api": "openai",
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "stopReason": "stop",
            "timestamp": 2,
            "usage": usage,
        },
    )


def _journal(*entries: dict, session_id: str = SESSION_ID) -> bytes:
    header = {"type": "session", "version": 3, "id": session_id, "timestamp": TS, "cwd": "/workspace"}
    lines = [json.dumps(header, separators=(",", ":")), *(json.dumps(row, separators=(",", ":")) for row in entries)]
    return (_slot() + "\n".join(lines) + "\n").encode()


def _link(**overrides: object) -> dict:
    value = {
        "schema_version": "session_link.v1",
        "run_id": "run-1",
        "step_id": "task",
        "visit_key": "task__v1",
        "workflow_workspace": "/workspace",
        "scaffold_relpath": "workflows/generated/prompt-aaaaaaaaaaaa",
        "paths": {
            "state": "state.json",
            "metadata": "provider_sessions/task__v1.json",
            "live": "provider_sessions/task__v1",
            "snapshot": "provider_sessions/task__v1.snapshot",
            "conf": None,
        },
        "session": {"id": SESSION_ID, "primary_basename": PRIMARY},
        "digests": {
            "live_manifest_sha256": HEX,
            "snapshot_manifest_sha256": HEX,
            "conf_manifest_sha256": None,
            "scaffold_manifest_sha256": HEX,
            "authored_prompt_sha256": HEX,
            "composed_prompt_sha256": HEX,
            "source_sha256": HEX,
            "semantic_contract_sha256": HEX,
        },
        "provider": {"name": "omp", "model": "gpt-5.6-sol", "lane": "ambient"},
        "scaffold_identity": HEX,
        "launch": {
            "argv": ["run", "--lane", "omp", "--model", "gpt-5.6-sol"],
            "env_names": ["HOME", "PATH"],
        },
        "confinement": None,
    }
    value.update(overrides)
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_session_link_shape_is_exact_and_closed() -> None:
    parsed = parse_session_link_bytes(_canonical(_link()))
    assert parsed.run_id == "run-1"
    assert parsed.session_id == SESSION_ID
    assert parsed.primary_basename == PRIMARY

    for bad in (
        {**_link(), "unknown": 1},
        {**_link(), "schema_version": "session_link.v2"},
        {**_link(), "run_id": ""},
        {**_link(), "scaffold_relpath": "../escape"},
        {**_link(), "workflow_workspace": "relative"},
        {**_link(), "session": {"id": SESSION_ID, "primary_basename": "a/b.jsonl"}},
    ):
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            parse_session_link_bytes(_canonical(bad))


def test_session_link_rejects_unsafe_visit_fixed_paths_and_workspace_spelling() -> None:
    for bad in (
        {**_link(), "visit_key": "../foreign"},
        {**_link(), "workflow_workspace": "/workspace/../other"},
        {**_link(), "workflow_workspace": "/workspace//other"},
        {**_link(), "paths": {**_link()["paths"], "metadata": "provider_sessions/other.json"}},
        {**_link(), "paths": {**_link()["paths"], "live": "provider_sessions/other"}},
        {**_link(), "paths": {**_link()["paths"], "snapshot": "provider_sessions/other.snapshot"}},
    ):
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            parse_session_link_bytes(_canonical(bad))


def test_session_link_nested_objects_and_nulls_are_closed() -> None:
    bad_values = []
    for member in ("paths", "session", "digests", "provider", "launch"):
        bad = _link()
        bad[member] = {**bad[member], "unknown": 1}
        bad_values.append(bad)
    bad_values.extend(
        (
            {**_link(), "provider": {"name": "internal", "model": "m", "lane": "ambient"}},
            {**_link(), "digests": {**_link()["digests"], "conf_manifest_sha256": "A" * 64}},
            {**_link(), "launch": {"argv": ["omp"], "env_names": ["PATH", "HOME"]}},
            {**_link(), "confinement": {}},
        )
    )
    for bad in bad_values:
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            parse_session_link_bytes(_canonical(bad))


def test_extracts_first_pre_assistant_user_string_byte_for_byte() -> None:
    prompt = "line one\nline two\n"
    parsed = parse_journal_bytes(
        _journal(_entry("reset_boundary", "r", None), _user(prompt, parent="r"), _assistant()),
        relpath=PRIMARY,
    )
    assert extract_prompt_bytes(parsed) == prompt.encode()


def test_extracts_only_nonempty_closed_text_arrays_joined_once() -> None:
    content = [
        {"type": "text", "text": "first", "textSignature": "sig"},
        {"type": "text", "text": "second"},
    ]
    parsed = parse_journal_bytes(_journal(_user(content)), relpath=PRIMARY)
    assert extract_prompt_bytes(parsed) == b"first\nsecond"

    for malformed in (
        [],
        [{"type": "text", "text": ""}],
        [{"type": "image", "data": "YQ==", "mimeType": "image/png"}],
    ):
        parsed = parse_journal_bytes(_journal(_user(malformed)), relpath=PRIMARY)
        with pytest.raises(PromptSessionError, match="prompt_import_invalid"):
            extract_prompt_bytes(parsed)

def test_extract_rejects_agent_branch_missing_and_post_assistant() -> None:
    cases = (
        _journal(_entry("reset_boundary", "r", None)),
        _journal(_user("", parent=None)),
        _journal(_entry("session_init", "i", None, systemPrompt="s", task="t", tools=[], agent="child"), _user("x", parent="i")),
        _journal(_entry("reset_boundary", "r", None), _assistant("a", "r"), _user("late", "u2", "a")),
    )
    for data in cases:
        parsed = parse_journal_bytes(data, relpath=PRIMARY)
        with pytest.raises(PromptSessionError, match="prompt_import_invalid"):
            extract_prompt_bytes(parsed)


def test_extract_uses_first_pre_assistant_user_when_branch_has_two() -> None:
    parsed = parse_journal_bytes(
        _journal(_entry("reset_boundary", "r", None), _user("first", "u1", "r"), _user("second", "u2", "u1")),
        relpath=PRIMARY,
    )
    assert extract_prompt_bytes(parsed) == b"first"


def _write_index_run(
    runs_root: Path,
    run_id: str,
    *,
    session_id: str = SESSION_ID,
    primary: str = PRIMARY,
    continuation: dict | None = None,
) -> dict:
    run = runs_root / run_id
    sessions = run / "provider_sessions"
    live = sessions / "task__v1"
    snapshot = sessions / "task__v1.snapshot"
    live.mkdir(parents=True)
    snapshot.mkdir()
    data = _journal(_user("source prompt"), _settled_assistant(), session_id=session_id)
    (live / primary).write_bytes(data)
    (snapshot / primary).write_bytes(data)
    state = {
        "run_id": run_id,
        "status": "completed",
        "artifact_versions": {
            "omp_session": [{
                "version": 1,
                "value": session_id,
                "producer": "task",
                "producer_name": "task",
                "step_index": 0,
            }],
        },
    }
    (run / "state.json").write_text(json.dumps(state), encoding="utf-8")
    from orchestrator.providers.omp_pin import OMP_BINARY_PIN
    from orchestrator.providers.omp_launch_contract import (
        PROFILE_ENV_NAMES,
        build_fresh_adapter_argv,
        build_interactive_argv,
        resolved_adapter_command,
    )
    argv = list(
        build_fresh_adapter_argv(
            "omp",
            "gpt-5.6-sol",
            session_dir=str(live),
        )
    )
    frame = {
        "type": "orchestrator.omp_launch.v1",
        "lane": "ambient",
        "persistence": "fresh",
        "binary": {
            "platform": OMP_BINARY_PIN.platform,
            "arch": OMP_BINARY_PIN.arch,
            "version": OMP_BINARY_PIN.version,
            "sha256": OMP_BINARY_PIN.executable_sha256,
        },
        "child": {
            "argv": argv,
            "cwd": str(runs_root.parent.resolve()),
            "env_names": sorted(PROFILE_ENV_NAMES),
            "exit_code": 0,
        },
        "session": {
            "id": session_id,
            "visit_key": "task__v1",
            "primary_relpath": primary,
            "primary_sha256": hashlib.sha256(data).hexdigest(),
        },
        "conf": {"manifest_sha256": None},
        "confinement": None,
                "observed": {"advisor_relpaths": [], "child_relpaths": []},
    }
    metadata = {
        "run_id": run_id,
        "provider": "omp",
        "step_name": "task",
        "step_id": "task",
        "visit_count": 1,
        "mode": "fresh",
        "step_status": "completed",
        "publication_state": "published",
        "session_id": session_id,
        "metadata_mode": "omp_json_stdout",
        "command_variant": "fresh_command",
        "resolved_command": resolved_adapter_command(argv),
        "started_at": TS,
        "updated_at": TS,
        "captured_transport_bytes": 0,
        "parser_summary": {"launch_frame": frame},
        "transport_spool_path": None,
    }
    (sessions / "task__v1.json").write_text(json.dumps(metadata), encoding="utf-8")
    from orchestrator.providers.omp_session_manifest import build_session_manifest

    def manifest_digest(path: Path) -> str:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            return build_session_manifest(fd).manifest_sha256
        finally:
            os.close(fd)

    link = _link(
        run_id=run_id,
        workflow_workspace=str(runs_root.parent.resolve()),
        session={"id": session_id, "primary_basename": primary},
        digests={
            **_link()["digests"],
            "live_manifest_sha256": manifest_digest(live),
            "snapshot_manifest_sha256": manifest_digest(snapshot),
            "composed_prompt_sha256": hashlib.sha256(b"source prompt").hexdigest(),
        },
        launch={"argv": argv, "env_names": sorted(PROFILE_ENV_NAMES)},
    )
    raw = _canonical(link)
    (sessions / "task__v1.session-link.json").write_bytes(raw)
    if continuation is not None:
        chain = sessions / "task__v1.continuations"
        chain.mkdir()
        (chain / "1.json").write_bytes(
            _canonical(
                {
                    "schema_version": "session_continuation.v1",
                    "sequence": 1,
                    "previous_sha256": hashlib.sha256(raw).hexdigest(),
                    "status": "failed",
                    "mode": "fork",
                    "source": {
                        "session_id": session_id,
                        "primary_basename": primary,
                        "journal_sha256": hashlib.sha256(data).hexdigest(),
                    },
                    "result": {
                        "session_id": None,
                        "primary_basename": None,
                        "journal_sha256": None,
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
                    "conf_manifest_sha256": None,
                    "launch": {
                        "argv": list(
                            build_interactive_argv(
                                "omp",
                                link["provider"]["model"],
                                private_binary=str(
                                    runs_root.parent / "cache" / "omp-i1"
                                    / "private" / OMP_BINARY_PIN.executable_sha256
                                    / ("attempt-" + "0" * 32) / "omp"
                                ),
                                live_dir=str(live),
                                mode="fork",
                                source_session_id=session_id,
                                workspace=link["workflow_workspace"],
                            )
                        ),
                        "env_names": sorted(PROFILE_ENV_NAMES),
                    },
                    "confinement": None,
                    "pre_live_manifest_sha256": link["digests"]["live_manifest_sha256"],
                    "post_live_manifest_sha256": None,
                    **continuation,
                }
            )
        )
    return link


def test_exact_lookup_precedence_and_no_prefix_or_path_inputs(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_index_run(runs, "run-1")
    assert resolve_prompt_session(runs, "run-1").run_id == "run-1"
    assert resolve_prompt_session(runs, SESSION_ID).session_id == SESSION_ID
    assert resolve_prompt_session(runs, PRIMARY).primary_basename == PRIMARY
    for value in ("run", SESSION_ID[:8], PRIMARY[:12], ".", "..", "/tmp/x", "a/b", "a\\\\b", "a\\x00b"):
        with pytest.raises(PromptSessionError, match="prompt_session_not_found"):
            resolve_prompt_session(runs, value)


def test_exact_lookup_reports_only_run_visit_identity_on_ambiguity(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_index_run(runs, "run-1")
    _write_index_run(runs, "run-2")
    with pytest.raises(PromptSessionError, match=r"prompt_session_ambiguous: run-1/task__v1, run-2/task__v1"):
        resolve_prompt_session(runs, SESSION_ID)


def test_lookup_ignores_stray_run_directory_before_session_tier(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _write_index_run(runs, "run-1")
    (runs / SESSION_ID).mkdir()
    assert resolve_prompt_session(runs, SESSION_ID).run_id == "run-1"




def test_lookup_rejects_primary_read_after_manifest_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator import prompt_session_chain

    runs = tmp_path / "runs"
    _write_index_run(runs, "run-1")
    original = prompt_session_chain.read_regular_file
    primary_reads = 0

    def drift(root_fd, relative, **kwargs):
        nonlocal primary_reads
        data = original(root_fd, relative, **kwargs)
        if relative == PRIMARY:
            primary_reads += 1
            if primary_reads == 2:
                return data + b" "
        return data

    monkeypatch.setattr(prompt_session_chain, "read_regular_file", drift)
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        resolve_prompt_session(runs, "run-1")


def test_lookup_rejects_actual_transport_spool_and_link_filename_mismatch(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    _write_index_run(runs, "run-1")
    sessions = runs / "run-1" / "provider_sessions"
    (sessions / "task__v1.transport.log").write_bytes(b"")
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        resolve_prompt_session(runs, "run-1")
    (sessions / "task__v1.transport.log").unlink()
    (sessions / "task__v1.session-link.json").rename(
        sessions / "other.session-link.json"
    )
    with pytest.raises(PromptSessionError, match="session_link_invalid"):
        resolve_prompt_session(runs, "run-1")



def test_failed_or_malformed_continuation_blocks_exact_run_and_is_not_indexed(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    link = _write_index_run(runs, "run-1", continuation={})
    with pytest.raises(PromptSessionError, match="prompt_session_blocked"):
        resolve_prompt_session(runs, "run-1")
    with pytest.raises(PromptSessionError, match="prompt_session_not_found"):
        resolve_prompt_session(runs, SESSION_ID)

    with pytest.raises(PromptSessionError, match="session_continuation_invalid"):
        validate_continuation_chain(_canonical(link), [_canonical({"schema_version": "bad"})])
