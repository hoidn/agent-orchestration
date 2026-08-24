"""RED contract tests for the pinned OMP JSON transport codec (X3)."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from orchestrator.providers import ProviderSessionMetadataMode
from orchestrator.providers.types import OmpTransportExpectation

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "omp" / "protocol"

TRANSIENT = "transient.stdout.jsonl"
FRESH = "fresh-session.stdout.jsonl"

EXPECTED_BINARY = {
    "platform": "linux",
    "arch": "x86_64",
    "version": "17.3.4",
    "sha256": "f" * 64,
}


def _omp_transport_module() -> ModuleType:
    try:
        return importlib.import_module("orchestrator.providers.omp_transport")
    except ModuleNotFoundError as exc:
        if exc.name != "orchestrator.providers.omp_transport":
            raise
        pytest.fail("provider OMP JSON transport codec is not implemented")


def _new_accumulator(**kwargs: Any) -> Any:
    module = _omp_transport_module()
    return module.OmpJsonStdoutAccumulator(**kwargs)


def _fixture(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


def _header_id(name: str) -> str:
    for raw_line in _fixture(name).split(b"\n"):
        if raw_line.startswith(b'{"type":"session"'):
            return json.loads(raw_line)["id"]
    raise AssertionError(f"{name} has no session header")


def _jsonl(event: Any) -> bytes:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def _expectation(**overrides: Any) -> OmpTransportExpectation:
    base: dict[str, Any] = {
        "lane": "ambient",
        "persistence": "none",
        "binary": EXPECTED_BINARY,
        "stdout_session_id": None,
        "visit_key": None,
        "child_argv": (),
        "conf_manifest_sha256": None,
        "confinement_policy_sha256": None,
        "observed_relpaths": (),
    }
    base.update(overrides)
    return OmpTransportExpectation(**base)


def _launch_frame(
    session_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "type": "orchestrator.omp_launch.v1",
        "lane": "ambient",
        "persistence": "none",
        "binary": EXPECTED_BINARY,
        "child": {
            "argv": [],
            "cwd": "/tmp/work",
            "env_names": [],
            "exit_code": 0,
        },
        "session": {
            "id": session_id,
            "visit_key": None,
            "primary_relpath": None,
            "primary_sha256": None,
        },
        "conf": {"manifest_sha256": None},
        "confinement": None,
        "observed": {"advisor_relpaths": [], "child_relpaths": []},
    }
    frame.update(overrides)
    return frame


def _finalize(
    accumulator: Any,
    *,
    require_terminal: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=require_terminal,
    )
    return (
        dict(metadata) if metadata is not None else None,
        dict(error) if error is not None else None,
    )


def _fixture_lines(name: str = TRANSIENT) -> list[bytes]:
    return [line for line in _fixture(name).split(b"\n") if line]


def _stream_with_update(update_event: dict[str, Any]) -> bytes:
    """Fixture stream with one extra update inside the open assistant lifecycle."""
    lines = _fixture_lines()
    head = b"\n".join(lines[:6]) + b"\n"  # through assistant message_start
    tail = b"\n".join(lines[6:]) + b"\n"  # fixture updates..agent_end
    return (
        head
        + _jsonl({"type": "message_update", "assistantMessageEvent": update_event})
        + b"\n"
        + tail
    )


def _stream_with_extra_assistant_lifecycle(message: dict[str, Any]) -> bytes:
    """Fixture stream plus one full assistant lifecycle before the fixture's own."""
    lines = _fixture_lines()
    head = b"\n".join(lines[:5]) + b"\n"  # through user message_end
    tail = b"\n".join(lines[5:]) + b"\n"  # fixture assistant lifecycle..agent_end
    start = _jsonl({"type": "message_start", "message": {"role": "assistant"}})
    end = _jsonl({"type": "message_end", "message": message})
    return head + start + b"\n" + end + b"\n" + tail


def _stream_with_replaced_assistant_message(message: dict[str, Any]) -> bytes:
    """Fixture stream with line 10's closed assistant message replaced."""
    parsed = [json.loads(line) for line in _fixture_lines()]
    parsed[9]["message"] = message
    return "\n".join(
        json.dumps(obj, separators=(",", ":")) for obj in parsed
    ).encode("utf-8") + b"\n"


def _assert_transport_error(error: dict[str, Any] | None) -> None:
    assert error is not None
    assert error["type"] == "provider_session_transport_error"
    assert isinstance(error.get("message"), str) and error["message"]
    json.dumps(error)


# ---------------------------------------------------------------------------
# Framing: UTF-8, LF, final non-LF object, duplicates, non-finite, whitespace
# ---------------------------------------------------------------------------


def test_omp_transport_accepts_captured_transient_fixture_with_frame():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["session_id"] == _header_id(TRANSIENT)
    assert metadata["event_count"] == 11
    assert metadata["final_provider"] == "openai-codex"
    assert metadata["final_model"] == "gpt-5.6-sol"
    assert metadata["total_tokens"] == 6599
    assert metadata["total_cost"] == 0.006624
    assert metadata["messages"] == [
        {
            "provider": "openai-codex",
            "model": "gpt-5.6-sol",
            "usage": {
                "input": 706,
                "output": 5,
                "cacheRead": 5888,
                "cacheWrite": 0,
                "totalTokens": 6599,
                "cost": {
                    "input": 0.00353,
                    "output": 0.00015000000000000001,
                    "cacheRead": 0.002944,
                    "cacheWrite": 0,
                    "total": 0.006624,
                },
            },
            "stop_reason": "stop",
        }
    ]
    assert metadata["launch_frame"]["type"] == "orchestrator.omp_launch.v1"
    assert accumulator.normalized_stdout == "OK"


def test_omp_transport_accepts_captured_fresh_fixture_with_persisted_frame():
    session_id = _header_id(FRESH)
    expectation = _expectation(
        lane="no-tools",
        persistence="fresh",
        visit_key="step-1__v1",
        confinement_policy_sha256="a" * 64,
        observed_relpaths=("provider_sessions/step-1__v1/1.jsonl",),
    )
    accumulator = _new_accumulator(expectation=expectation)
    accumulator.feed(_fixture(FRESH))
    frame = _launch_frame(
        session_id,
        lane="no-tools",
        persistence="fresh",
        session={
            "id": session_id,
            "visit_key": "step-1__v1",
            "primary_relpath": "provider_sessions/step-1__v1/1.jsonl",
            "primary_sha256": "b" * 64,
        },
        confinement={
            "schema_version": "omp_write_confinement.v1",
            "landlock_abi": 5,
            "policy_sha256": "a" * 64,
        },
        observed={
            "advisor_relpaths": [],
            "child_relpaths": ["provider_sessions/step-1__v1/1.jsonl"],
        },
    )
    accumulator.feed(_jsonl(frame) + b"\n")

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 11
    assert metadata["launch_frame"]["persistence"] == "fresh"
    assert accumulator.normalized_stdout == "OK"


def test_omp_transport_accepts_split_and_coalesced_chunks_and_final_non_lf():
    accumulator = _new_accumulator(expectation=_expectation())
    payload = _fixture(TRANSIENT) + _jsonl(_launch_frame(_header_id(TRANSIENT)))
    assert not payload.endswith(b"\n")
    snowman_escape = "\\u2603".encode("ascii")
    assert snowman_escape not in payload

    # Split a multibyte UTF-8 character across chunks, then coalesce.
    marker = _header_id(TRANSIENT).encode("utf-8")
    split_at = payload.index(marker) + 4
    accumulator.feed(payload[:split_at])
    accumulator.feed(payload[split_at:split_at + 2])
    accumulator.feed(payload[split_at + 2:])

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 11


def test_omp_transport_rejects_invalid_utf8_bytes():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(b"\xff\n")

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_rejects_duplicate_json_keys():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(b'{"type":"agent_start","type":"turn_start"}\n')

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize(
    "line",
    (
        b'{"type":"agent_start","x":1e999}\n',
        b'{"type":"agent_start","x":Infinity}\n',
        b'{"type":"agent_start","x":-Infinity}\n',
        b'{"type":"agent_start","x":NaN}\n',
    ),
)
def test_omp_transport_rejects_non_finite_json_numbers(line: bytes):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(line)

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize("line", (b"   \n", b"\t\n", b"\r\n", b"\x0b\n"))
def test_omp_transport_rejects_whitespace_only_lines(line: bytes):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(line)

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize("line", (b"[]\n", b'"text"\n', b"42\n", b"null\n"))
def test_omp_transport_requires_every_line_to_be_a_json_object(line: bytes):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(line)

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_empty_lines_are_skipped_and_never_counted():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(b"\n\n" + _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n")

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 11


# ---------------------------------------------------------------------------
# Session header: sole first object, admitted fields, closed keys
# ---------------------------------------------------------------------------


def test_omp_transport_requires_sole_first_session_header():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        b"\n".join(
            (
                _jsonl({"type": "agent_start"}),
                *_fixture(TRANSIENT).split(b"\n"),
            )
        )
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)
    assert accumulator.snapshot().status == "invalid"


def test_omp_transport_rejects_duplicate_session_header():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            {
                "type": "session",
                "version": 3,
                "id": "second-id",
                "timestamp": "2026-08-23T22:33:14.831Z",
                "cwd": "/tmp/work",
            }
        )
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_header_accepts_every_admitted_optional_field():
    header = {
        "type": "session",
        "version": 3,
        "id": "header-optional",
        "timestamp": "2026-08-23T22:33:14.831Z",
        "cwd": "/tmp/work",
        "title": "a title",
        "titleSource": "user",
        "parentSession": "parent-id",
        "providerPromptCacheKey": "cache-key",
        "additionalDirectories": ["/tmp/one", "/tmp/two"],
        "previousSessionFiles": ["/tmp/old.jsonl"],
    }
    accumulator = _new_accumulator(
        expectation=_expectation(stdout_session_id="header-optional")
    )
    accumulator.feed(_jsonl(header) + b"\n")
    accumulator.feed(_jsonl({"type": "agent_start"}) + b"\n")
    accumulator.feed(_jsonl({"type": "turn_start"}) + b"\n")
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "assistant", "content": []}}) + b"\n"
    )
    accumulator.feed(
        _jsonl(_minimal_assistant_message_end()) + b"\n"
    )
    accumulator.feed(
        _jsonl({"type": "agent_end", "messages": []}) + b"\n"
    )
    accumulator.feed(
        _jsonl(_launch_frame("header-optional")) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["session_id"] == "header-optional"


def _minimal_assistant_message_end() -> dict[str, Any]:
    return {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "api": "api",
            "provider": "provider",
            "model": "model",
            "timestamp": 1,
            "stopReason": "stop",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {
                "input": 1,
                "output": 1,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 2,
                "cost": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "total": 0,
                },
            },
        },
    }


def test_omp_transport_header_rejects_unknown_keys():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        _jsonl(
            {
                "type": "session",
                "id": "id",
                "timestamp": "2026-08-23T22:33:14.831Z",
                "cwd": "/tmp/work",
                "mystery": 1,
            }
        )
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize(
    "mutations",
    (
        {"id": ""},
        {"id": 7},
        {"timestamp": "not-a-timestamp"},
        {"timestamp": "2026-08-23 22:33:14"},
        {"cwd": "relative/path"},
        {"cwd": ""},
        {"version": "3"},
        {"titleSource": "admin"},
        {"title": 7},
        {"additionalDirectories": "not-an-array"},
        {"previousSessionFiles": [7]},
        {"parentSession": 7},
    ),
)
def test_omp_transport_header_rejects_malformed_required_and_optional_fields(
    mutations: dict[str, Any],
):
    header = {
        "type": "session",
        "version": 3,
        "id": "id",
        "timestamp": "2026-08-23T22:33:14.831Z",
        "cwd": "/tmp/work",
    }
    header.update(mutations)
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_jsonl(header) + b"\n")

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


# ---------------------------------------------------------------------------
# Recognized event shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_type", ("agent_start", "turn_start"))
def test_omp_transport_agent_and_turn_start_contain_only_type(
    event_type: str,
):
    lines = _fixture_lines()
    index = {"agent_start": 1, "turn_start": 2}[event_type]
    assert json.loads(lines[index]) == {"type": event_type}
    malformed = {**json.loads(lines[index]), "extra": 1}
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        b"\n".join(lines[:index]) + b"\n" + _jsonl(malformed) + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_tool_execution_shapes_are_closed():
    valid_events = (
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "bash",
            "args": {"command": "ls"},
            "intent": "list",
        },
        {
            "type": "tool_execution_update",
            "toolCallId": "call-1",
            "toolName": "bash",
            "args": {"command": "ls"},
            "partialResult": "file1\n",
        },
        {
            "type": "tool_execution_end",
            "toolCallId": "call-1",
            "toolName": "bash",
            "result": {"output": "file1\n"},
            "isError": False,
        },
    )
    lines = _fixture_lines()
    head = b"\n".join(lines[:11]) + b"\n"  # through turn_end
    tail = b"\n".join(lines[11:]) + b"\n"  # terminal agent_end
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        head
        + b"\n".join(_jsonl(event) for event in valid_events)
        + b"\n"
        + tail
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 14


@pytest.mark.parametrize(
    "event",
    (
        {"type": "tool_execution_start", "toolName": "bash", "args": {}},
        {"type": "tool_execution_start", "toolCallId": "c", "toolName": "", "args": {}},
        {"type": "tool_execution_start", "toolCallId": "c", "toolName": "bash", "args": {}, "intent": 7},
        {"type": "tool_execution_start", "toolCallId": "c", "toolName": "bash", "args": {}, "surprise": 1},
        {"type": "tool_execution_update", "toolCallId": "c", "toolName": "bash"},
        {"type": "tool_execution_end", "toolCallId": "c", "toolName": "bash", "result": 1, "isError": "no"},
        {"type": "tool_execution_end", "toolCallId": "c", "toolName": "bash", "extra": 1},
    ),
)
def test_omp_transport_malformed_tool_events_fail_closed(event: dict[str, Any]):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(_jsonl(event) + b"\n")

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_message_lifecycle_requires_matching_role():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            {
                "type": "message_start",
                "message": {"role": "assistant", "content": []},
            }
        )
        + b"\n"
    )
    accumulator.feed(
        _jsonl(
            {
                "type": "message_end",
                "message": {"role": "user", "content": []},
            }
        )
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_message_lifecycle_overlap_and_orphan_fail():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "user"}}) + b"\n"
    )
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "user"}}) + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)

    orphan = _new_accumulator(expectation=_expectation())
    orphan.feed(_fixture(TRANSIENT))
    orphan.feed(
        _jsonl({"type": "message_end", "message": {"role": "user"}}) + b"\n"
    )

    _, orphan_error = _finalize(orphan, require_terminal=False)

    _assert_transport_error(orphan_error)


def test_omp_transport_message_update_requires_open_assistant_lifecycle():
    lines = _fixture_lines()
    head = b"\n".join(lines[:5]) + b"\n"  # through user message_end
    update = _jsonl(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "x"},
        }
    ) + b"\n"
    no_lifecycle = _new_accumulator(expectation=_expectation())
    no_lifecycle.feed(head + update)

    _, error = _finalize(no_lifecycle, require_terminal=False)

    _assert_transport_error(error)

    user_lifecycle = _new_accumulator(expectation=_expectation())
    user_lifecycle.feed(
        head
        + _jsonl({"type": "message_start", "message": {"role": "user"}}) + b"\n"
        + update
    )

    _, user_error = _finalize(user_lifecycle, require_terminal=False)

    _assert_transport_error(user_error)


def test_omp_transport_message_update_never_carries_outer_message():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        _stream_with_update({"type": "start"})
        + b"\n"
        + _jsonl({"type": "message_update", "assistantMessageEvent": {"type": "start"}, "message": {"role": "assistant"}})
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize(
    "event",
    (
        {"type": "text_start", "contentIndex": -1},
        {"type": "text_start", "contentIndex": "0"},
        {"type": "text_delta", "contentIndex": 0},
        {"type": "text_end", "contentIndex": 0},
        {"type": "thinking_delta", "contentIndex": 0, "delta": 7},
        {"type": "image_end", "content": {"type": "image", "data": "abc", "mimeType": "image/png"}},
        {"type": "toolcall_end"},
        {"type": "done", "reason": "error"},
        {"type": "error", "reason": "stop"},
        {"type": "partial"},
        {"type": "message"},
        {"type": "error", "reason": "error", "snapshot": {}},
    ),
)
def test_omp_transport_assistant_message_event_union_is_closed(
    event: dict[str, Any],
):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_update(event))

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize(
    "event",
    (
        {"type": "text_start", "contentIndex": 0},
        {"type": "text_delta", "contentIndex": 0, "delta": "d"},
        {"type": "thinking_start", "contentIndex": 1},
        {"type": "thinking_delta", "contentIndex": 1, "delta": "d"},
        {"type": "toolcall_start", "contentIndex": 2},
        {"type": "text_end", "contentIndex": 0, "content": "c"},
        {"type": "thinking_end", "contentIndex": 1, "content": "c"},
        {
            "type": "toolcall_end",
            "toolCall": {"id": "t", "name": "bash", "arguments": {}},
        },
        {"type": "done", "reason": "stop"},
    ),
)
def test_omp_transport_assistant_message_event_union_admits_pinned_kinds(
    event: dict[str, Any],
):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_update(event))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 12


@pytest.mark.parametrize(
    "mutations",
    (
        {"role": "system"},
        {"api": ""},
        {"provider": ""},
        {"model": ""},
        {"timestamp": "now"},
        {"stopReason": "cancelled"},
        {"content": "not-an-array"},
        {"usage": None},
    ),
)
def test_omp_transport_closed_assistant_message_requires_mandatory_fields(
    mutations: dict[str, Any],
):
    event = _minimal_assistant_message_end()
    event["message"].update(mutations)
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_extra_assistant_lifecycle(event["message"]))

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


@pytest.mark.parametrize(
    "block",
    (
        {"type": "text", "text": "ok", "textSignature": "sig"},
        {
            "type": "image",
            "data": "aGVsbG8=",
            "mimeType": "image/png",
            "detail": "low",
        },
        {"type": "tool_call", "id": "t1", "name": "bash", "arguments": {}},
        {"type": "tool_use", "id": "t2", "name": "read", "arguments": {"path": "/tmp/x"}},
        {"type": "thinking", "payload": {"tokens": [1]}},
    ),
)
def test_omp_transport_content_block_kinds_are_pinned(block: dict[str, Any]):
    message = _minimal_assistant_message_end()["message"]
    message["content"] = [block]
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_extra_assistant_lifecycle(message))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    expected_text = block["text"] if block["type"] == "text" else ""
    assert accumulator.normalized_stdout == (
        expected_text + "\nOK" if expected_text else "OK"
    )


@pytest.mark.parametrize(
    "block",
    (
        {"type": "text", "text": "ok", "extra": 1},
        {"type": "text", "text": 7},
        {"type": "image", "data": "aGVsbG8=", "mimeType": ""},
        {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png", "detail": "huge"},
        {"type": "tool_call", "id": "", "name": "bash", "arguments": {}},
        {"type": "tool_call", "id": "t", "name": "bash", "arguments": "{}"},
        {"type": ""},
    ),
)
def test_omp_transport_malformed_content_blocks_fail_closed(
    block: dict[str, Any],
):
    message = _minimal_assistant_message_end()["message"]
    message["content"] = [block]
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_replaced_assistant_message(message))

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_usage_requires_core_fields_and_rejects_unknown():
    message = _minimal_assistant_message_end()["message"]
    message["usage"] = {"input": 1}
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_replaced_assistant_message(message))

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)

    message = _minimal_assistant_message_end()["message"]
    message["usage"]["surprise"] = 1
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_replaced_assistant_message(message))

    _, surprise_error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(surprise_error)


def test_omp_transport_usage_admits_optional_fields_and_rejects_negatives():
    usage = {
        "input": 1,
        "output": 1,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 2,
        "cost": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
            "total": 0,
        },
        "contextTokens": 1,
        "premiumRequests": 2,
        "reasoningTokens": 3,
        "orchestration": {"input": 1, "cacheRead": 0, "output": 1},
        "cttl": {"ephemeral5m": 0, "ephemeral1h": 1},
        "server": {"webSearch": 1, "webFetch": 0},
    }
    message = _minimal_assistant_message_end()["message"]
    message["usage"] = usage
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_replaced_assistant_message(message))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None

    message = _minimal_assistant_message_end()["message"]
    message["usage"]["input"] = -1
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_replaced_assistant_message(message))

    _, negative_error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(negative_error)


def test_omp_transport_turn_end_shape_is_closed():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            {
                "type": "turn_end",
                "message": {"role": "assistant"},
                "toolResults": [],
                "extra": 1,
            }
        )
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)

    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "turn_end", "message": {"role": "assistant"}})
        + b"\n"
    )

    _, missing_error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(missing_error)


def test_omp_transport_text_blocks_and_messages_join_in_validated_order():
    first = _minimal_assistant_message_end()
    first["message"]["content"] = [
        {"type": "text", "text": "one"},
        {"type": "text", "text": "two"},
    ]
    second = _minimal_assistant_message_end()
    second["message"]["content"] = [{"type": "text", "text": "three"}]
    second["message"]["provider"] = "provider-two"
    lines = _fixture_lines()
    head = b"\n".join(lines[:5]) + b"\n"  # through user message_end
    start = _jsonl({"type": "message_start", "message": {"role": "assistant"}})
    agent_end = _jsonl({"type": "agent_end", "messages": []}) + b"\n"
    emitted: list[str] = []
    accumulator = _new_accumulator(
        expectation=_expectation(),
        assistant_text_callback=emitted.append,
    )
    accumulator.feed(
        head
        + start + b"\n" + _jsonl(first) + b"\n"
        + start + b"\n" + _jsonl(second) + b"\n"
        + agent_end
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert accumulator.normalized_stdout == "one\ntwo\nthree"
    assert emitted == ["one\ntwo", "three"]
    assert [row["provider"] for row in metadata["messages"]] == [
        "provider",
        "provider-two",
    ]


def test_omp_transport_error_update_requires_matching_stop_reason():
    # The fixture's message_end closes with stopReason "stop", which does not
    # match the preceding error update reason; the lifecycle must fail.
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        _stream_with_update(
            {"type": "error", "reason": "error"},
        )
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_error_update_admitted_with_matching_stop_and_recovery():
    failed = _minimal_assistant_message_end()
    failed["message"]["stopReason"] = "aborted"
    failed["message"]["api"] = "openai-codex-responses"
    lines = _fixture_lines()
    head = b"\n".join(lines[:6]) + b"\n"  # through assistant message_start
    update = _jsonl(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "error", "reason": "aborted"},
        }
    ) + b"\n"
    next_start = _jsonl(
        {"type": "message_start", "message": {"role": "assistant"}}
    ) + b"\n"
    agent_end = _jsonl({"type": "agent_end", "messages": []}) + b"\n"
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        head
        + update
        + _jsonl(failed) + b"\n"
        + next_start
        + _jsonl(_minimal_assistant_message_end()) + b"\n"
        + agent_end
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 10


# ---------------------------------------------------------------------------
# Terminal semantics and settlement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "terminal_value",
    (None, True, False),
)
def test_omp_transport_agent_end_is_terminal_semantics(
    terminal_value: bool | None,
):
    agent_end = {"type": "agent_end", "messages": []}
    if terminal_value is not None:
        agent_end["isTerminal"] = terminal_value
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(_jsonl(agent_end) + b"\n")
    frame = _launch_frame(_header_id(TRANSIENT))
    if terminal_value is False:
        # Nonterminal returns to streaming: a later terminal is still required.
        accumulator.feed(_jsonl({"type": "agent_end", "messages": []}) + b"\n")
    accumulator.feed(_jsonl(frame) + b"\n")

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None


def test_omp_transport_nonterminal_agent_end_returns_to_streaming():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(_jsonl({"type": "agent_end", "messages": [], "isTerminal": False}) + b"\n")
    accumulator.feed(_jsonl({"type": "turn_start"}) + b"\n")
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "assistant"}}) + b"\n"
    )
    accumulator.feed(_jsonl(_minimal_assistant_message_end()) + b"\n")
    accumulator.feed(_jsonl({"type": "agent_end", "messages": []}) + b"\n")
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 16


def test_omp_transport_terminal_requires_last_closed_assistant_stop():
    event = _minimal_assistant_message_end()
    event["message"]["stopReason"] = "length"
    lines = _fixture_lines()
    head = b"\n".join(lines[:6]) + b"\n"  # through assistant message_start
    agent_end = _jsonl({"type": "agent_end", "messages": []}) + b"\n"
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(head + _jsonl(event) + b"\n" + agent_end)
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_terminal_requires_last_assistant_without_tool_call():
    event = _minimal_assistant_message_end()
    event["message"]["content"] = [
        {"type": "tool_call", "id": "t", "name": "bash", "arguments": {}}
    ]
    lines = _fixture_lines()
    head = b"\n".join(lines[:6]) + b"\n"  # through assistant message_start
    agent_end = _jsonl({"type": "agent_end", "messages": []}) + b"\n"
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(head + _jsonl(event) + b"\n" + agent_end)
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_earlier_provider_error_is_recovered_by_later_stop():
    failed = _minimal_assistant_message_end()
    failed["message"]["stopReason"] = "error"
    failed["message"]["api"] = "openai-codex-responses"
    lines = _fixture_lines()
    head = b"\n".join(lines[:6]) + b"\n"  # through assistant message_start
    next_start = _jsonl(
        {"type": "message_start", "message": {"role": "assistant"}}
    ) + b"\n"
    agent_end = _jsonl({"type": "agent_end", "messages": []}) + b"\n"
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(
        head
        + _jsonl(failed) + b"\n"
        + next_start
        + _jsonl(_minimal_assistant_message_end()) + b"\n"
        + agent_end
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["final_provider"] == "provider"


def test_omp_transport_open_lifecycle_at_terminal_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "user"}}) + b"\n"
    )
    accumulator.feed(_jsonl({"type": "agent_end", "messages": []}) + b"\n")
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_post_terminal_assistant_lifecycle_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "assistant"}})
        + b"\n"
    )

    metadata, error = _finalize(accumulator, require_terminal=False)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_late_custom_pairs_are_tolerated_after_settlement():
    emitted: list[str] = []
    accumulator = _new_accumulator(
        expectation=_expectation(),
        assistant_text_callback=emitted.append,
    )
    accumulator.feed(_fixture(TRANSIENT))
    custom_start = _jsonl(
        {"type": "custom", "message": {"role": "custom", "content": []}}
    )
    accumulator.feed(custom_start + b"\n")
    accumulator.feed(
        _jsonl(
            {
                "type": "custom",
                "message": {"role": "custom", "content": []},
            }
        )
        + b"\n"
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 13
    assert accumulator.normalized_stdout == "OK"
    assert emitted == ["OK"]


def test_omp_transport_custom_before_settlement_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    head = b"\n".join(_fixture_lines()[:11]) + b"\n"
    accumulator.feed(head)
    accumulator.feed(
        _jsonl({"type": "custom", "message": {"role": "custom"}}) + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


# ---------------------------------------------------------------------------
# Opaque unknown events
# ---------------------------------------------------------------------------


def test_omp_transport_opaque_unknown_events_increment_event_count_only():
    emitted: list[str] = []
    accumulator = _new_accumulator(
        expectation=_expectation(),
        assistant_text_callback=emitted.append,
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        b"\n".join(
            (
                _jsonl({"type": "future.event", "payload": {"secret": "body"}}),
                _jsonl({"type": "another.event", "data": [1, 2]}),
            )
        )
        + b"\n"
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 13
    assert metadata["session_id"] == _header_id(TRANSIENT)
    assert accumulator.normalized_stdout == "OK"
    assert emitted == ["OK"]
    assert "payload" not in json.dumps(metadata)
    assert "secret" not in json.dumps(metadata)


def test_omp_transport_unknown_events_cannot_rescue_missing_terminal():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT)[: _fixture(TRANSIENT).rindex(b"\n")])
    # Drop the terminal agent_end line, then feed unknowns and a frame.
    terminal_line = _fixture(TRANSIENT).split(b"\n")[-2]
    assert b'"type":"agent_end"' in terminal_line
    accumulator.feed(
        b"\n".join(
            (
                _jsonl({"type": "opaque.one"}),
                _jsonl({"type": "opaque.two"}),
                _launch_frame(_header_id(TRANSIENT)).__class__ and _jsonl(
                    _launch_frame(_header_id(TRANSIENT))
                ),
            )
        )
        + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_unknown_events_cannot_rescue_missing_frame():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        b"\n".join(
            (
                _jsonl({"type": "opaque.one"}),
                _jsonl({"type": "opaque.two"}),
            )
        )
        + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_unknown_events_cannot_open_or_close_lifecycle():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "user"}}) + b"\n"
    )
    accumulator.feed(_jsonl({"type": "opaque.lifecycle"}) + b"\n")
    accumulator.feed(_jsonl({"type": "agent_end", "messages": []}) + b"\n")
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_malformed_recognized_events_still_fail_closed():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            {
                "type": "message_end",
                "message": {"role": "assistant", "surprise": True},
            }
        )
        + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_blank_or_non_string_type_fails_even_unknown_shape():
    for raw_line in (
        b'{"type":""}\n',
        b'{"type":7}\n',
        b'{"type":["x"]}\n',
        b'{"type":null}\n',
        b'{}\n',
    ):
        accumulator = _new_accumulator(expectation=_expectation())
        accumulator.feed(_fixture(TRANSIENT))
        accumulator.feed(raw_line)

        _, error = _finalize(accumulator, require_terminal=False)

        _assert_transport_error(error)


# ---------------------------------------------------------------------------
# Terminal/frame ordering and EOF
# ---------------------------------------------------------------------------


def test_omp_transport_frame_before_terminal_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    terminal_line = _fixture(TRANSIENT).split(b"\n")[-2]
    without_terminal = _fixture(TRANSIENT).replace(
        terminal_line + b"\n", b""
    )
    assert b'"type":"agent_end"' not in without_terminal
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(without_terminal)
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_duplicate_or_spoofed_frame_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    _, error = _finalize(accumulator, require_terminal=False)

    _assert_transport_error(error)


def test_omp_transport_eof_before_frame_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_data_after_frame_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )
    accumulator.feed(_jsonl({"type": "agent_start"}) + b"\n")

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_eof_with_open_lifecycle_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "message_start", "message": {"role": "user"}}) + b"\n"
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_zero_closed_assistant_messages_fails():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    # Replace every assistant lifecycle: reopen as user role only.
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    raw = _fixture(TRANSIENT)
    lines = [
        line
        for line in raw.split(b"\n")
        if line
        and b'"type":"message_start","message":{"role":"assistant"' not in line
        and b'"type":"message_end","message":{"role":"assistant"' not in line
        and b'"type":"message_update"' not in line
    ]
    accumulator.feed(b"\n".join(lines) + b"\n")
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


# ---------------------------------------------------------------------------
# Adapter frame: closed schema, expectation matching, confinement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    (
        {"type": "orchestrator.omp_launch.v2"},
        {"lane": "conf"},
        {"persistence": "fresh"},
        {"binary": {"platform": "darwin"}},
        {"session": {"id": "other-id", "visit_key": None, "primary_relpath": None, "primary_sha256": None}},
        {"child": {"argv": [], "cwd": "relative", "env_names": [], "exit_code": 0}},
        {"child": {"argv": [], "cwd": "/tmp", "env_names": [], "exit_code": 0, "surprise": 1}},
        {"child": {"argv": [], "cwd": "/tmp", "env_names": [], "exit_code": "0"}},
        {"observed": {"advisor_relpaths": [], "child_relpaths": ["x"]}},
        {"surprise": 1},
        {"session": {"id": "id", "visit_key": None}},
        {"conf": {}},
        {"confinement": {"schema_version": "omp_write_confinement.v1", "landlock_abi": 3, "policy_sha256": "a" * 64}},
    ),
)
def test_omp_transport_frame_mismatch_or_malformed_fails(
    overrides: dict[str, Any],
):
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    frame = _launch_frame(_header_id(TRANSIENT))
    for key, value in overrides.items():
        frame[key] = value
    accumulator.feed(_jsonl(frame) + b"\n")

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_frame_binary_pin_must_match_expectation():
    accumulator = _new_accumulator(
        expectation=_expectation(
            binary={**EXPECTED_BINARY, "sha256": "e" * 64}
        )
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_frame_session_id_must_match_header():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame("different-session-id")) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_frame_visit_key_and_conf_must_match_expectation():
    accumulator = _new_accumulator(
        expectation=_expectation(visit_key="step-1__v1")
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    _, error = _finalize(accumulator)

    _assert_transport_error(error)

    accumulator = _new_accumulator(
        expectation=_expectation(conf_manifest_sha256="c" * 64)
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    _, conf_error = _finalize(accumulator)

    _assert_transport_error(conf_error)


def test_omp_transport_fresh_persistence_nullability_is_checked():
    expectation = _expectation(persistence="fresh", visit_key="step-1__v1")
    accumulator = _new_accumulator(expectation=expectation)
    accumulator.feed(_fixture(TRANSIENT))
    # Fresh persistence requires non-null primary session fields.
    accumulator.feed(
        _jsonl(
            _launch_frame(
                _header_id(TRANSIENT),
                persistence="fresh",
                session={
                    "id": _header_id(TRANSIENT),
                    "visit_key": "step-1__v1",
                    "primary_relpath": None,
                    "primary_sha256": None,
                },
            )
        )
        + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_ambient_lane_requires_null_confinement():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            _launch_frame(
                _header_id(TRANSIENT),
                confinement={
                    "schema_version": "omp_write_confinement.v1",
                    "landlock_abi": 5,
                    "policy_sha256": "a" * 64,
                },
            )
        )
        + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


@pytest.mark.parametrize(
    "confinement",
    (
        None,
        {"schema_version": "omp_write_confinement.v2", "landlock_abi": 5, "policy_sha256": "a" * 64},
        {"schema_version": "omp_write_confinement.v1", "landlock_abi": 2, "policy_sha256": "a" * 64},
        {"schema_version": "omp_write_confinement.v1", "landlock_abi": 5, "policy_sha256": "b" * 64},
        {"schema_version": "omp_write_confinement.v1", "landlock_abi": "5", "policy_sha256": "a" * 64},
        {"schema_version": "omp_write_confinement.v1", "landlock_abi": 5},
    ),
)
def test_omp_transport_profile_lane_confinement_must_match_expectation(
    confinement: dict[str, Any] | None,
):
    accumulator = _new_accumulator(
        expectation=_expectation(confinement_policy_sha256="a" * 64)
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            _launch_frame(_header_id(TRANSIENT), confinement=confinement)
        )
        + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


def test_omp_transport_frame_observed_inventory_must_match_expectation():
    relpaths = ("provider_sessions/step-1__v1/1.jsonl",)
    accumulator = _new_accumulator(
        expectation=_expectation(
            persistence="fresh",
            visit_key="step-1__v1",
            observed_relpaths=relpaths,
        )
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(
            _launch_frame(
                _header_id(TRANSIENT),
                persistence="fresh",
                session={
                    "id": _header_id(TRANSIENT),
                    "visit_key": "step-1__v1",
                    "primary_relpath": "provider_sessions/step-1__v1/1.jsonl",
                    "primary_sha256": "b" * 64,
                },
                observed={
                    "advisor_relpaths": [],
                    "child_relpaths": ["provider_sessions/step-1__v1/other.jsonl"],
                },
            )
        )
        + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert metadata is None
    _assert_transport_error(error)


# ---------------------------------------------------------------------------
# Callbacks and finalize semantics
# ---------------------------------------------------------------------------


def test_omp_transport_callback_runs_once_per_closed_assistant_message():
    emitted: list[str] = []
    accumulator = _new_accumulator(
        expectation=_expectation(),
        assistant_text_callback=emitted.append,
    )
    accumulator.feed(_fixture(TRANSIENT))

    assert emitted == ["OK"]


def test_omp_transport_callback_exception_does_not_mutate_parse_state():
    def _explode(_text: str) -> None:
        raise RuntimeError("display failure")

    accumulator = _new_accumulator(
        expectation=_expectation(),
        assistant_text_callback=_explode,
    )
    accumulator.feed(_fixture(TRANSIENT))
    before = accumulator.snapshot()

    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert metadata["event_count"] == 11
    assert accumulator.snapshot() == before or accumulator.snapshot().terminal_seen


def test_omp_transport_updates_and_unknowns_never_invoke_callbacks():
    emitted: list[str] = []
    accumulator = _new_accumulator(
        expectation=_expectation(),
        assistant_text_callback=emitted.append,
    )
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl({"type": "opaque.event"}) + b"\n"
    )
    accumulator.feed(
        _jsonl(
            {
                "type": "message_update",
                "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "extra"},
            }
        )
        + b"\n"
    )

    assert emitted == ["OK"]


def test_omp_transport_provisional_finalize_cannot_weaken_mandatory_finalize():
    incomplete = _new_accumulator(expectation=_expectation())
    incomplete.feed(_fixture(TRANSIENT))

    provisional_metadata, provisional_error = _finalize(
        incomplete, require_terminal=False
    )
    assert provisional_metadata is None
    assert provisional_error is None

    metadata, error = _finalize(incomplete, require_terminal=True)

    assert metadata is None
    _assert_transport_error(error)
    assert incomplete.snapshot().terminal_seen is True


def test_omp_transport_provisional_finalize_cannot_settle_a_complete_stream():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    provisional_metadata, provisional_error = _finalize(
        accumulator, require_terminal=False
    )

    metadata, error = _finalize(accumulator, require_terminal=True)

    assert provisional_error is None
    assert error is None
    assert metadata is not None
    assert provisional_metadata == metadata
    # Repeated authoritative finalization is idempotent.
    again_metadata, again_error = _finalize(accumulator, require_terminal=True)
    assert again_error is None
    assert again_metadata == metadata


def test_omp_transport_snapshot_reports_identity_and_terminal():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))

    snapshot = accumulator.snapshot()
    assert snapshot.status == "unique"
    assert snapshot.session_ids == (_header_id(TRANSIENT),)
    assert snapshot.terminal_seen is True
    assert snapshot.resume_boundary_seen is False
    assert snapshot.error is None
    assert snapshot.assistant_text_is_eligible(expected_session_id=None)


# ---------------------------------------------------------------------------
# Credential-minimized metadata
# ---------------------------------------------------------------------------


def test_omp_transport_normalized_metadata_keys_are_closed():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    assert set(metadata) == {
        "session_id",
        "event_count",
        "messages",
        "total_tokens",
        "total_cost",
        "final_provider",
        "final_model",
        "launch_frame",
    }
    assert set(metadata["messages"][0]) == {
        "provider",
        "model",
        "usage",
        "stop_reason",
    }


def test_omp_transport_metadata_never_contains_assistant_text_or_payloads():
    secret_text = "the api key is sk-abc123 and \x1b]0;title\x07"
    message = _minimal_assistant_message_end()["message"]
    message["content"] = [
        {"type": "text", "text": secret_text},
        {"type": "image", "data": "aGVsbG8=", "mimeType": "image/png"},
        {"type": "tool_call", "id": "t", "name": "bash", "arguments": {"command": "cat /etc/passwd"}},
    ]
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_extra_assistant_lifecycle(message))
    accumulator.feed(
        _jsonl({"type": "opaque.body", "body": {"credential": "sekrit"}})
        + b"\n"
    )
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert metadata is not None
    serialized = json.dumps(metadata)
    assert "sk-abc123" not in serialized
    assert "cat /etc/passwd" not in serialized
    assert "aGVsbG8=" not in serialized
    assert "sekrit" not in serialized
    assert accumulator.normalized_stdout == secret_text + "\nOK"


def test_omp_transport_authoritative_output_keeps_non_printable_text_exact():
    text = "line1\x00\x1b]0;x\x07\r\x7fline2"
    message = _minimal_assistant_message_end()["message"]
    message["content"] = [{"type": "text", "text": text}]
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_stream_with_replaced_assistant_message(message))
    accumulator.feed(
        _jsonl(_launch_frame(_header_id(TRANSIENT))) + b"\n"
    )

    metadata, error = _finalize(accumulator)

    assert error is None
    assert accumulator.normalized_stdout == text
    assert metadata is not None


def test_omp_transport_snapshot_is_immutable_and_error_projection_is_frozen():
    accumulator = _new_accumulator(expectation=_expectation())
    accumulator.feed(_fixture(TRANSIENT))
    accumulator.feed(b"\xff\n")
    snapshot = accumulator.snapshot()

    assert snapshot.status == "invalid"
    assert snapshot.error is not None
    with pytest.raises(TypeError):
        snapshot.error["message"] = "mutated"
    with pytest.raises(TypeError):
        snapshot.error["context"]["line"] = 999

    metadata, error = _finalize(accumulator, require_terminal=False)

    assert metadata is None
    assert isinstance(error, dict)
    json.dumps(error)
