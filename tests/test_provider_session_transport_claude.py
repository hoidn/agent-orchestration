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
