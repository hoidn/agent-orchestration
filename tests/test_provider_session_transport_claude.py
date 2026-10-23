"""`claude -p --output-format stream-json` is a structural session codec with a terminal result event."""
from __future__ import annotations

import json

from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.session_transport import create_session_transport_accumulator
from orchestrator.providers.types import ProviderSessionMetadataMode

SID = "1930ae6b-5267-4eec-b1e1-b430dad86844"


def _events(*rows: dict) -> bytes:
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def _init(sid=SID):
    return {"type": "system", "subtype": "init", "session_id": sid, "model": "haiku"}


def _assistant(text, sid=SID):
    return {"type": "assistant", "session_id": sid, "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _result(sid=SID, is_error=False):
    return {"type": "result", "subtype": "error" if is_error else "success", "is_error": is_error,
            "session_id": sid, "result": "done", "duration_ms": 5}


def test_mode_is_registered_and_selected_structurally() -> None:
    mode = ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value
    assert mode == "claude_stream_json_stdout"
    acc = create_session_transport_accumulator(mode)
    assert acc is not None and acc.event_count == 0


def test_finalize_binds_session_id_assistant_text_and_terminal() -> None:
    texts = []
    acc = create_session_transport_accumulator("claude_stream_json_stdout", assistant_text_callback=texts.append)
    acc.feed(_events(_init(), _assistant("hello "), _assistant("world")))
    snapshot = acc.snapshot()
    assert (snapshot.status, snapshot.session_ids, snapshot.terminal_seen) == ("unique", (SID,), False)
    acc.feed(_events(_result()))
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert error is None
    assert metadata["session_id"] == SID and metadata["event_count"] == 4
    assert metadata["normalized_stdout"] == "hello world" and texts == ["hello ", "world"]
    assert (metadata["result_subtype"], metadata["is_error"]) == ("success", False)


def test_tool_only_turn_reports_tool_lifecycle_without_normalizing_payloads() -> None:
    activity = []
    acc = create_session_transport_accumulator(
        "claude_stream_json_stdout", tool_activity_callback=activity.append
    )
    start = {
        "type": "assistant",
        "session_id": SID,
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "Bash",
                    "input": {"command": "PRIVATE COMMAND"},
                }
            ]
        },
    }
    result = {
        "type": "user",
        "session_id": SID,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-1",
                    "content": "PRIVATE RESULT",
                }
            ]
        },
    }
    stream = _events(_init(), start, result, _result())
    acc.feed(stream[:37])
    acc.feed(stream[37:])

    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)

    assert error is None
    assert activity == ["Tool started: Bash", "Tool completed: Bash"]
    assert metadata["normalized_stdout"] == ""
    assert "PRIVATE" not in " ".join(activity)


def test_unmatched_or_malformed_tool_blocks_are_ignored_and_callback_is_best_effort() -> None:
    activity = []

    def broken_callback(_notice):
        raise RuntimeError("display failed")

    acc = create_session_transport_accumulator(
        "claude_stream_json_stdout", tool_activity_callback=broken_callback
    )
    acc.feed(
        _events(
            _init(),
            {
                "type": "assistant",
                "session_id": SID,
                "message": {
                    "content": [
                        {"type": "tool_use", "name": "missing-id"},
                        {"type": "tool_use", "id": "tool-2", "name": "Read"},
                    ]
                },
            },
            {
                "type": "user",
                "session_id": SID,
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "unknown"},
                        {"type": "tool_result", "tool_use_id": "tool-2", "is_error": True},
                    ]
                },
            },
            _result(),
        )
    )

    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)

    assert error is None
    assert metadata["normalized_stdout"] == ""
    assert acc.snapshot().status == "unique"


def test_claude_callbacks_preserve_text_and_each_tool_order_in_one_event() -> None:
    emissions = []
    acc = create_session_transport_accumulator(
        "claude_stream_json_stdout",
        assistant_text_callback=lambda text: emissions.append(("text", text)),
        tool_activity_callback=lambda text: emissions.append(("activity", text)),
    )
    acc.feed(
        _events(
            _init(),
            {
                "type": "assistant",
                "session_id": SID,
                "message": {
                    "content": [
                        {"type": "text", "text": "before"},
                        {"type": "tool_use", "id": "tool-a", "name": "Bash", "input": {}},
                        {"type": "text", "text": "between"},
                        {"type": "tool_use", "id": "tool-b", "name": "Read", "input": {}},
                        {"type": "text", "text": "after"},
                    ]
                },
            },
            {
                "type": "user",
                "session_id": SID,
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tool-a"},
                        {"type": "tool_result", "tool_use_id": "tool-b", "is_error": True},
                    ]
                },
            },
            _result(),
        )
    )

    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)

    assert error is None
    assert metadata["normalized_stdout"] == "beforebetweenafter"
    assert emissions == [
        ("text", "before"),
        ("activity", "Tool started: Bash"),
        ("text", "between"),
        ("activity", "Tool started: Read"),
        ("text", "after"),
        ("activity", "Tool completed: Bash"),
        ("activity", "Tool failed: Read"),
    ]


def test_claude_malformed_error_flag_does_not_complete_or_consume_tool_use() -> None:
    activity = []
    acc = create_session_transport_accumulator(
        "claude_stream_json_stdout", tool_activity_callback=activity.append
    )
    acc.feed(
        _events(
            _init(),
            {"type": "assistant", "session_id": SID, "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Bash"}]}},
            {"type": "user", "session_id": SID, "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-1", "is_error": []}]}},
            {"type": "user", "session_id": SID, "message": {"content": [{"type": "tool_result", "tool_use_id": "tool-1", "is_error": True}]}},
            _result(),
        )
    )

    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)

    assert error is None
    assert metadata["normalized_stdout"] == ""
    assert activity == ["Tool started: Bash", "Tool failed: Bash"]


def test_missing_result_event_is_an_error_not_a_session() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(_events(_init(), _assistant("partial")))
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert metadata is None and error["type"] == "provider_session_transport_error"
    assert "terminal" in error["message"]


def test_resume_must_match_requested_session_and_rejects_mixed_ids() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(_events(_init(), _result()))
    _metadata, error = acc.finalize(expected_session_id="other", require_terminal=True)
    assert error is not None and error["context"]["observed_session_id"] == SID
    mixed = create_session_transport_accumulator("claude_stream_json_stdout")
    mixed.feed(_events(_init(), _init("22222222-2222-4222-8222-222222222222"), _result()))
    assert mixed.snapshot().status == "ambiguous"


def test_non_json_line_invalidates_without_raising() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(b"not json\n")
    assert acc.snapshot().status == "invalid"


def test_invalid_stream_finalizes_to_a_transport_error() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(_events(_init()) + b"not json\n")
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert metadata is None and error["context"]["line"] == 2


def test_claude_unrestricted_workspace_declares_session_support_without_changing_its_command() -> None:
    template = ProviderRegistry().get("claude_unrestricted_workspace")
    assert template.command == ["claude", "-p", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    support = template.session_support
    assert support.metadata_mode == "claude_stream_json_stdout" and support.turn_boundary_resume is False
    assert support.fresh_command[:4] == ["claude", "-p", "--output-format", "stream-json"] and "--verbose" in support.fresh_command
    assert support.resume_command.count("${SESSION_ID}") == 1 and "--resume" in support.resume_command
    assert "${PROMPT}" not in support.fresh_command + support.resume_command
    assert template.validate() == []
    assert ProviderRegistry().get("claude").session_support is None
