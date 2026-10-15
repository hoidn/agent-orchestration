"""Native-store adapters read position and completion evidence; they never write."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers.native_store import NativePosition, NativeStoreError, native_store_adapter

CODEX_SID = "01a13777-79ec-7511-8b2b-42a6111e33cf"
CLAUDE_SID = "1930ae6b-5267-4eec-b1e1-b430dad86844"


def _jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _codex_rows(turns: list[tuple[str, str, bool]]):
    rows = [{"type": "session_meta", "payload": {"id": CODEX_SID}}]
    for turn_id, marker, complete in turns:
        rows.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id}})
        rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": CODEX_SID,
                     "item": {"id": f"u-{turn_id}", "type": "UserMessage", "content": [{"text_elements": [marker]}]}}})
        if complete:
            rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": CODEX_SID,
                         "item": {"id": f"a-{turn_id}", "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": "{}"}]}}})
            rows.append({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id, "last_agent_message": "{}"}})
    return rows


def _claude_rows(turns: list[tuple[str, str, bool]]):
    rows, parent = [], None
    for prompt_id, marker, complete in turns:
        user_id = f"user-{prompt_id}"
        rows.append({"type": "user", "uuid": user_id, "parentUuid": parent, "sessionId": CLAUDE_SID, "promptId": prompt_id,
                     "isSidechain": False, "message": {"role": "user", "content": marker}})
        if complete:
            final_id = f"assistant-{prompt_id}"
            rows.append({"type": "assistant", "uuid": final_id, "parentUuid": user_id, "sessionId": CLAUDE_SID, "promptId": prompt_id,
                         "isSidechain": False, "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}})
            parent = final_id
    return rows


@pytest.mark.parametrize("mode, sid, rows_for, home_env, relpath", [
    ("codex_exec_jsonl_stdout", CODEX_SID, _codex_rows, "CODEX_HOME", f"sessions/2026/10/14/rollout-2026-10-14T00-00-00-{CODEX_SID}.jsonl"),
    ("claude_stream_json_stdout", CLAUDE_SID, _claude_rows, "CLAUDE_CONFIG_DIR", f"projects/-tmp-ws/{CLAUDE_SID}.jsonl"),
])
def test_head_and_completed_turn_follow_the_store(tmp_path, monkeypatch, mode, sid, rows_for, home_env, relpath) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv(home_env, str(home))
    adapter = native_store_adapter(mode)
    assert adapter.metadata_mode == mode
    assert adapter.locate(sid).path is None  # nothing yet
    path = home / relpath
    _jsonl(path, rows_for([("t1", "attempt-1/result.json", True)]))
    located = adapter.locate(sid)
    assert (located.path, located.ambiguous) == (path, False)
    head = adapter.head(path)
    assert head.locator == sid and head.open_turn is False and head.position.turn_id == "t1"
    first = adapter.completed_turn(path, after=None, prompt_marker="attempt-1/result.json")
    assert first is not None and first.position == head.position
    _jsonl(path, rows_for([("t1", "attempt-1/result.json", True), ("t2", "attempt-2/result.json", True)]))
    second = adapter.completed_turn(path, after=head.position, prompt_marker="attempt-2/result.json")
    assert second.position.turn_id == "t2" and second.position.end_line > head.position.end_line
    assert adapter.completed_turn(path, after=None, prompt_marker="attempt-2/result.json") is None  # wrong predecessor


@pytest.mark.parametrize("mode, sid, rows_for, home_env, relpath", [
    ("codex_exec_jsonl_stdout", CODEX_SID, _codex_rows, "CODEX_HOME", f"sessions/a/rollout-x-{CODEX_SID}.jsonl"),
    ("claude_stream_json_stdout", CLAUDE_SID, _claude_rows, "CLAUDE_CONFIG_DIR", f"projects/p/{CLAUDE_SID}.jsonl"),
])
def test_open_turn_and_ambiguity_are_reported_not_guessed(tmp_path, monkeypatch, mode, sid, rows_for, home_env, relpath) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv(home_env, str(home))
    adapter = native_store_adapter(mode)
    path = home / relpath
    _jsonl(path, rows_for([("t1", "m1", True), ("t2", "m2", False)]))
    head = adapter.head(path)
    assert head.open_turn is True and head.position.turn_id == "t1"
    assert adapter.completed_turn(path, after=head.position, prompt_marker="m2") is None
    copy = path.with_name("copy-" + path.name) if mode.startswith("codex") else path.parent.parent / "q" / path.name
    _jsonl(copy, rows_for([("t1", "m1", True)]))
    located = adapter.locate(sid)
    assert located.path is None and located.ambiguous is True


def test_unknown_mode_has_no_adapter_and_env_is_not_required(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert native_store_adapter("omp_json_stdout") is None
    assert native_store_adapter("codex_exec_jsonl_stdout").home == Path.home() / ".codex"


def test_codex_accumulator_counts_completed_turns() -> None:
    from orchestrator.providers.session_transport import CodexExecJsonlAccumulator
    acc = CodexExecJsonlAccumulator()
    acc.feed(b'{"type":"thread.started","thread_id":"%s"}\n{"type":"turn.started"}\n{"type":"turn.completed"}\n' % CODEX_SID.encode())
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert error is None and metadata["turns_completed"] == 1


# --- Claude completion rule beyond the brief's fixtures -------------------------------------------------------------

def _claude_structured_turn(prompt_id: str, marker: str, parent, *, attachment: bool = True):
    user, assistant, completion = f"user-{prompt_id}", f"tool-asst-{prompt_id}", f"done-{prompt_id}"
    rows = [
        {"type": "user", "uuid": user, "parentUuid": parent, "sessionId": CLAUDE_SID, "promptId": prompt_id,
         "message": {"role": "user", "content": [{"type": "text", "text": marker}]}},
        {"type": "assistant", "uuid": assistant, "parentUuid": user, "sessionId": CLAUDE_SID,
         "message": {"role": "assistant", "stop_reason": "tool_use",
                     "content": [{"type": "tool_use", "id": f"tu-{prompt_id}", "name": "StructuredOutput", "input": {"ok": True}}]}},
    ]
    if attachment:
        rows.append({"type": "attachment", "uuid": f"att-{prompt_id}", "parentUuid": assistant, "sessionId": CLAUDE_SID,
                     "attachment": {"type": "structured_output", "toolUseID": f"tu-{prompt_id}", "data": {"ok": True}}})
    rows.append({"type": "user", "uuid": completion, "parentUuid": assistant, "sessionId": CLAUDE_SID, "promptId": prompt_id,
                 "sourceToolAssistantUUID": assistant, "toolEndsTurn": True,
                 "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"tu-{prompt_id}", "content": "ok"}]}})
    return rows


def test_claude_structured_output_terminal_binds_the_turn(tmp_path) -> None:
    path = tmp_path / f"{CLAUDE_SID}.jsonl"
    _jsonl(path, _claude_structured_turn("p1", "m1", None))
    turn = native_store_adapter("claude_stream_json_stdout").completed_turn(path, after=None, prompt_marker="m1")
    assert turn is not None and turn.position == NativePosition("p1", 4) and turn.user_line == 1


def test_claude_structured_output_without_its_attachment_is_incomplete(tmp_path) -> None:
    path = tmp_path / f"{CLAUDE_SID}.jsonl"
    _jsonl(path, _claude_structured_turn("p1", "m1", None, attachment=False))
    head = native_store_adapter("claude_stream_json_stdout").head(path)
    assert (head.position, head.open_turn) == (None, True)


def test_claude_turn_with_two_finals_is_incomplete(tmp_path) -> None:
    rows = _claude_rows([("p1", "m1", True)])
    rows.append({**rows[-1], "uuid": "assistant-again", "parentUuid": "assistant-p1"})
    path = tmp_path / f"{CLAUDE_SID}.jsonl"
    _jsonl(path, rows)
    adapter = native_store_adapter("claude_stream_json_stdout")
    assert adapter.completed_turn(path, after=None, prompt_marker="m1") is None


def test_claude_turn_after_a_broken_turn_is_not_a_position(tmp_path) -> None:
    rows = _claude_rows([("p1", "m1", True), ("p2", "m2", True)])
    rows[2]["parentUuid"] = "elsewhere"  # p2 does not descend from p1's final
    path = tmp_path / f"{CLAUDE_SID}.jsonl"
    _jsonl(path, rows)
    head = native_store_adapter("claude_stream_json_stdout").head(path)
    assert (head.position, head.open_turn) == (NativePosition("p1", 2), True)


def test_position_record_round_trips_and_rejects_malformed_rows() -> None:
    position = NativePosition("t1", 3)
    assert NativePosition.from_record(position.record()) == position
    with pytest.raises(ValueError):
        NativePosition.from_record({"turn_id": "t1", "end_line": True})


# --- Codex strictness and reader error paths -------------------------------------------------------------------------

def _codex_store(tmp_path: Path, rows) -> Path:
    path = tmp_path / f"rollout-x-{CODEX_SID}.jsonl"
    _jsonl(path, rows)
    return path


def test_codex_turn_without_final_answer_is_not_bound(tmp_path) -> None:
    rows = _codex_rows([("t1", "m1", True)])
    del rows[3]  # the AgentMessage final_answer
    path = _codex_store(tmp_path, rows)
    assert native_store_adapter("codex_exec_jsonl_stdout").completed_turn(path, after=None, prompt_marker="m1") is None


@pytest.mark.parametrize("later_complete", [False, True], ids=["later-open-turn", "external-completed-turn"])
def test_codex_turn_followed_by_another_turn_is_not_bound(tmp_path, later_complete) -> None:
    path = _codex_store(tmp_path, _codex_rows([("t1", "m1", True), ("t2", "external", later_complete)]))
    assert native_store_adapter("codex_exec_jsonl_stdout").completed_turn(path, after=None, prompt_marker="m1") is None


def _overlapping_start():
    return _codex_rows([("t1", "m1", False), ("t2", "m2", True)])


def _repeated_start():
    rows = _codex_rows([("t1", "m1", True)])
    return rows + [{"type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}}]


def _item_outside_turn():
    rows = _codex_rows([("t1", "m1", True)])
    return rows + [{"type": "event_msg", "payload": {"type": "item_completed", "turn_id": "t1", "thread_id": CODEX_SID,
                                                     "item": {"id": "late", "type": "AgentMessage"}}}]


@pytest.mark.parametrize("rows_for", [_overlapping_start, _repeated_start, _item_outside_turn])
def test_codex_unsupported_lifecycle_raises(tmp_path, rows_for) -> None:
    path = _codex_store(tmp_path, rows_for())
    with pytest.raises(NativeStoreError):
        native_store_adapter("codex_exec_jsonl_stdout").head(path)


@pytest.mark.parametrize("text", [
    "{not json\n",
    '{"type": "session_meta", "type": "event_msg"}\n',
    '{"type": "session_meta", "payload": {"id": NaN}}\n',
], ids=["malformed", "duplicate-key", "nan"])
def test_unreadable_store_rows_raise(tmp_path, text) -> None:
    path = tmp_path / f"rollout-x-{CODEX_SID}.jsonl"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(NativeStoreError):
        native_store_adapter("codex_exec_jsonl_stdout").head(path)


@pytest.mark.parametrize("mode, home_env, store", [
    ("codex_exec_jsonl_stdout", "CODEX_HOME", "sessions"),
    ("claude_stream_json_stdout", "CLAUDE_CONFIG_DIR", "projects"),
])
@pytest.mark.parametrize("locator", ["../escape", "a/b", "*", "id[0]"])
def test_locate_rejects_a_locator_that_is_not_a_plain_id(tmp_path, monkeypatch, mode, home_env, store, locator) -> None:
    monkeypatch.setenv(home_env, str(tmp_path))
    (tmp_path / store).mkdir()
    with pytest.raises(NativeStoreError):
        native_store_adapter(mode).locate(locator)
