"""Contract tests for incremental provider-session transport parsing."""

from __future__ import annotations

import importlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import orchestrator.providers as provider_api
from orchestrator.providers import (
    InputMode,
    ProviderExecutor,
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from orchestrator.providers.types import ProviderInvocation


def _session_transport_module() -> ModuleType:
    try:
        return importlib.import_module("orchestrator.providers.session_transport")
    except ModuleNotFoundError as exc:
        if exc.name != "orchestrator.providers.session_transport":
            raise
        pytest.fail("provider session transport codec is not implemented")


def _new_accumulator(**kwargs: Any) -> Any:
    module = _session_transport_module()
    return module.CodexExecJsonlAccumulator(**kwargs)


def _jsonl_event(**event: Any) -> bytes:
    return json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def test_codex_jsonl_accumulator_handles_split_coalesced_chunks_and_one_eof_tail():
    accumulator = _new_accumulator()
    payload = b"\n".join(
        (
            _jsonl_event(type="thread.started", thread_id="thread-\N{SNOWMAN}"),
            _jsonl_event(
                type="assistant.message",
                role="assistant",
                text="first ",
            ),
            _jsonl_event(
                type="item.completed",
                item={"type": "agent_message", "text": "second"},
            ),
            _jsonl_event(type="turn.completed", thread_id="thread-\N{SNOWMAN}"),
        )
    )
    snowman_offset = payload.index("\N{SNOWMAN}".encode("utf-8"))
    chunks = (
        payload[: snowman_offset + 1],
        payload[snowman_offset + 1 : snowman_offset + 2],
        payload[snowman_offset + 2 : payload.index(b"\n") + 1],
        payload[payload.index(b"\n") + 1 : -7],
        payload[-7:],
    )

    for chunk in chunks:
        accumulator.feed(chunk)

    before_eof = accumulator.snapshot()
    assert before_eof.status == "unique"
    assert before_eof.session_ids == ("thread-\N{SNOWMAN}",)
    assert before_eof.terminal_seen is False

    first_result = accumulator.finalize(
        expected_session_id=None,
        require_terminal=True,
    )
    second_result = accumulator.finalize(
        expected_session_id=None,
        require_terminal=True,
    )

    assert first_result == second_result
    metadata, error = first_result
    assert error is None
    assert metadata == {
        "session_id": "thread-\N{SNOWMAN}",
        "normalized_stdout": "first second",
        "event_count": 4,
    }


def test_codex_jsonl_snapshot_exposes_real_thread_id_before_terminal():
    accumulator = _new_accumulator()

    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-real") + b"\n"
    )

    assert accumulator.snapshot() == _session_transport_module().SessionIdentitySnapshot(
        status="unique",
        session_ids=("thread-real",),
        terminal_seen=False,
        error=None,
    )

    accumulator.feed(
        _jsonl_event(
            type="item.completed",
            item={"type": "agent_message", "text": "working"},
        )
        + b"\n"
    )
    assert accumulator.snapshot().terminal_seen is False

    accumulator.feed(_jsonl_event(type="turn.completed") + b"\n")
    assert accumulator.snapshot().terminal_seen is True


def test_session_identity_snapshot_resume_boundary_defaults_false_and_is_immutable():
    snapshot = _session_transport_module().SessionIdentitySnapshot(
        status="missing",
        session_ids=(),
        terminal_seen=False,
    )

    assert snapshot.resume_boundary_seen is False
    with pytest.raises(FrozenInstanceError):
        snapshot.resume_boundary_seen = True


@pytest.mark.parametrize(
    (
        "status",
        "session_ids",
        "expected_session_id",
        "expected_eligible",
    ),
    (
        pytest.param("missing", (), None, True, id="missing-unconstrained"),
        pytest.param(
            "missing",
            (),
            "session-expected",
            True,
            id="missing-before-identity",
        ),
        pytest.param(
            "unique",
            ("session-observed",),
            None,
            True,
            id="unique-unconstrained",
        ),
        pytest.param(
            "unique",
            ("session-expected",),
            "session-expected",
            True,
            id="unique-match",
        ),
        pytest.param(
            "unique",
            ("session-other",),
            "session-expected",
            False,
            id="unique-mismatch",
        ),
        pytest.param(
            "ambiguous",
            ("session-expected", "session-other"),
            None,
            False,
            id="ambiguous-unconstrained",
        ),
        pytest.param(
            "ambiguous",
            ("session-expected", "session-other"),
            "session-expected",
            False,
            id="ambiguous-constrained",
        ),
        pytest.param(
            "invalid",
            (),
            None,
            False,
            id="invalid-unconstrained",
        ),
        pytest.param(
            "invalid",
            ("session-expected",),
            "session-expected",
            False,
            id="invalid-constrained",
        ),
    ),
)
def test_session_identity_snapshot_owns_assistant_text_eligibility(
    status: Any,
    session_ids: tuple[str, ...],
    expected_session_id: str | None,
    expected_eligible: bool,
) -> None:
    snapshot = _session_transport_module().SessionIdentitySnapshot(
        status=status,
        session_ids=session_ids,
        terminal_seen=False,
    )

    assert (
        snapshot.assistant_text_is_eligible(
            expected_session_id=expected_session_id,
        )
        is expected_eligible
    )


def test_codex_jsonl_resume_boundary_requires_exact_top_level_turn_started():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-boundary") + b"\n"
    )

    assert accumulator.snapshot().resume_boundary_seen is False

    for lookalike in (
        {"type": "turn.started.suffix"},
        {"type": "item.started", "status": "turn.started"},
        {"type": "item.started", "item": {"type": "turn.started"}},
        {"type": "turn", "status": "started"},
    ):
        accumulator.feed(_jsonl_event(**lookalike) + b"\n")
        assert accumulator.snapshot().resume_boundary_seen is False

    accumulator.feed(_jsonl_event(type="turn.started") + b"\n")

    assert accumulator.snapshot().resume_boundary_seen is True


def test_codex_jsonl_turn_started_can_bind_identity_in_the_same_event():
    accumulator = _new_accumulator()

    accumulator.feed(
        _jsonl_event(
            type="turn.started",
            thread_id="thread-same-event",
        )
        + b"\n"
    )

    snapshot = accumulator.snapshot()
    assert snapshot.status == "unique"
    assert snapshot.session_ids == ("thread-same-event",)
    assert snapshot.terminal_seen is False
    assert snapshot.resume_boundary_seen is True


@pytest.mark.parametrize(
    "event_type,identity_fields,expected_status",
    (
        ("turn.started", {"thread_id": None}, "invalid"),
        (
            "turn.started",
            {"thread_id": "thread-one", "session_id": "thread-two"},
            "ambiguous",
        ),
        ("turn.failed", {"thread_id": None}, "invalid"),
        (
            "turn.failed",
            {"thread_id": "thread-one", "session_id": "thread-two"},
            "ambiguous",
        ),
    ),
)
def test_codex_jsonl_turn_started_and_turn_failed_validate_identity_first(
    event_type: str,
    identity_fields: dict[str, Any],
    expected_status: str,
):
    accumulator = _new_accumulator()

    accumulator.feed(
        _jsonl_event(type=event_type, **identity_fields) + b"\n"
    )

    snapshot = accumulator.snapshot()
    assert snapshot.status == expected_status
    assert snapshot.terminal_seen is False
    assert snapshot.resume_boundary_seen is False


def test_codex_jsonl_turn_started_is_not_retroactive_or_post_terminal():
    early = _new_accumulator()
    early.feed(_jsonl_event(type="turn.started") + b"\n")
    early.feed(
        _jsonl_event(type="thread.started", thread_id="thread-early") + b"\n"
    )

    assert early.snapshot().status == "unique"
    assert early.snapshot().resume_boundary_seen is False

    terminal = _new_accumulator()
    terminal.feed(
        _jsonl_event(type="thread.started", thread_id="thread-terminal") + b"\n"
    )
    terminal.feed(_jsonl_event(type="turn.completed") + b"\n")
    terminal.feed(_jsonl_event(type="turn.started") + b"\n")

    assert terminal.snapshot().terminal_seen is True
    assert terminal.snapshot().resume_boundary_seen is False


def test_codex_jsonl_resume_boundary_handles_split_and_duplicate_turn_started():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-split") + b"\n"
    )
    marker = _jsonl_event(type="turn.started")
    split_at = len(marker) // 2

    accumulator.feed(marker[:split_at])
    assert accumulator.snapshot().resume_boundary_seen is False

    accumulator.feed(marker[split_at:] + b"\n" + marker + b"\n")

    assert accumulator.snapshot().resume_boundary_seen is True


def test_codex_jsonl_resume_boundary_handles_coalesced_turn_started_eof_tail():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-eof")
        + b"\n"
        + _jsonl_event(type="turn.started")
    )

    assert accumulator.snapshot().resume_boundary_seen is False

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    assert error is None
    assert metadata is not None
    assert accumulator.snapshot().resume_boundary_seen is True


@pytest.mark.parametrize(
    "later_event,expected_status,expected_terminal",
    (
        (
            {"type": "item.started", "thread_id": "thread-other"},
            "ambiguous",
            False,
        ),
        ({"type": "item.started", "thread_id": None}, "invalid", False),
        ({"type": "turn.completed"}, "unique", True),
    ),
)
def test_codex_jsonl_resume_boundary_observation_is_sticky(
    later_event: dict[str, Any],
    expected_status: str,
    expected_terminal: bool,
):
    accumulator = _new_accumulator()
    accumulator.feed(
        b"\n".join(
            (
                _jsonl_event(
                    type="thread.started",
                    thread_id="thread-sticky",
                ),
                _jsonl_event(type="turn.started"),
            )
        )
        + b"\n"
    )
    assert accumulator.snapshot().resume_boundary_seen is True

    accumulator.feed(_jsonl_event(**later_event) + b"\n")

    snapshot = accumulator.snapshot()
    assert snapshot.status == expected_status
    assert snapshot.terminal_seen is expected_terminal
    assert snapshot.resume_boundary_seen is True


@pytest.mark.parametrize("marker_before_failure", (False, True))
def test_codex_jsonl_turn_failed_is_terminal_and_durably_invalid(
    marker_before_failure: bool,
):
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-failed") + b"\n"
    )
    if marker_before_failure:
        accumulator.feed(_jsonl_event(type="turn.started") + b"\n")

    accumulator.feed(_jsonl_event(type="turn.failed") + b"\n")
    failed_snapshot = accumulator.snapshot()
    accumulator.feed(_jsonl_event(type="turn.started") + b"\n")
    accumulator.feed(_jsonl_event(type="turn.completed") + b"\n")
    assert accumulator.snapshot() == failed_snapshot

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    assert failed_snapshot.status == "invalid"
    assert failed_snapshot.terminal_seen is True
    assert failed_snapshot.resume_boundary_seen is marker_before_failure
    assert metadata is None
    assert error is not None
    assert error["type"] == "provider_session_transport_error"


@pytest.mark.parametrize(
    "lookalike",
    (
        {"type": "turn.failed.suffix"},
        {"type": "item.failed", "status": "turn.failed"},
        {"type": "item.failed", "item": {"type": "turn.failed"}},
        {"type": "turn", "status": "failed"},
    ),
)
def test_codex_jsonl_turn_failed_lookalikes_are_not_terminal(
    lookalike: dict[str, Any],
):
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-lookalike")
        + b"\n"
    )
    accumulator.feed(_jsonl_event(**lookalike) + b"\n")

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    snapshot = accumulator.snapshot()
    assert snapshot.status == "unique"
    assert snapshot.terminal_seen is False
    assert snapshot.resume_boundary_seen is False
    assert error is None
    assert metadata is not None


def test_session_transport_resume_boundary_capability_is_structural():
    module = _session_transport_module()

    assert module.supports_resume_boundary_observation(
        ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
    )
    assert not module.supports_resume_boundary_observation("unsupported-mode")
    assert not module.supports_resume_boundary_observation(None)


def test_codex_jsonl_retains_legacy_session_id_and_response_terminal():
    accumulator = _new_accumulator()
    accumulator.feed(
        b"\n".join(
            (
                _jsonl_event(type="session.started", session_id="sess-legacy"),
                _jsonl_event(type="response.completed", session_id="sess-legacy"),
            )
        )
        + b"\n"
    )

    metadata, error = accumulator.finalize(
        expected_session_id="sess-legacy",
        require_terminal=True,
    )

    assert error is None
    assert metadata is not None
    assert metadata["session_id"] == "sess-legacy"
    assert accumulator.snapshot().terminal_seen is True


def test_codex_jsonl_rejects_cross_key_identity_conflict():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(
            type="thread.started",
            thread_id="thread-one",
            session_id="thread-two",
        )
        + b"\n"
    )

    snapshot = accumulator.snapshot()
    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    assert snapshot.status == "ambiguous"
    assert snapshot.session_ids == ("thread-one", "thread-two")
    assert snapshot.error is not None
    assert metadata is None
    assert error is not None
    assert error["type"] == "provider_session_transport_error"


def test_codex_jsonl_rejects_identity_that_changes_after_unique_snapshot():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    assert accumulator.snapshot().status == "unique"

    accumulator.feed(
        _jsonl_event(type="turn.started", thread_id="thread-two") + b"\n"
    )
    accumulator.feed(
        _jsonl_event(type="turn.started", thread_id="thread-one") + b"\n"
    )

    snapshot = accumulator.snapshot()
    assert snapshot.status == "ambiguous"
    assert snapshot.session_ids == ("thread-one", "thread-two")
    assert snapshot.error is not None


def test_invalid_session_snapshot_error_rejects_outer_mutation():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id=None) + b"\n"
    )
    snapshot = accumulator.snapshot()
    assert snapshot.status == "invalid"
    assert snapshot.error is not None

    with pytest.raises(TypeError):
        snapshot.error["message"] = "mutated"

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )
    assert metadata is None
    assert isinstance(error, dict)
    json.dumps(error)


def test_invalid_session_snapshot_error_rejects_nested_context_mutation():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id=None) + b"\n"
    )
    snapshot = accumulator.snapshot()
    assert snapshot.error is not None
    context = snapshot.error["context"]

    with pytest.raises(TypeError):
        context["line"] = 999


def test_ambiguous_session_snapshot_error_rejects_outer_mutation():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    accumulator.feed(
        _jsonl_event(type="turn.started", thread_id="thread-two") + b"\n"
    )
    snapshot = accumulator.snapshot()
    assert snapshot.status == "ambiguous"
    assert snapshot.error is not None

    with pytest.raises(TypeError):
        snapshot.error["message"] = "mutated"

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )
    assert metadata is None
    assert isinstance(error, dict)
    json.dumps(error)


def test_ambiguous_session_snapshot_error_rejects_nested_context_mutation():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    accumulator.feed(
        _jsonl_event(type="turn.started", thread_id="thread-two") + b"\n"
    )
    snapshot = accumulator.snapshot()
    assert snapshot.error is not None
    context = snapshot.error["context"]

    with pytest.raises(TypeError):
        context["session_ids"] = ("mutated",)


def test_ambiguous_session_snapshot_error_rejects_nested_sequence_mutation():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    accumulator.feed(
        _jsonl_event(type="turn.started", thread_id="thread-two") + b"\n"
    )
    snapshot = accumulator.snapshot()
    assert snapshot.error is not None
    session_ids = snapshot.error["context"]["session_ids"]

    with pytest.raises((AttributeError, TypeError)):
        session_ids.append("mutated")


@pytest.mark.parametrize("key", ("thread_id", "session_id"))
@pytest.mark.parametrize("value", ("", None, 7))
def test_codex_jsonl_rejects_malformed_recognized_identity(key: str, value: Any):
    accumulator = _new_accumulator()
    accumulator.feed(_jsonl_event(type="thread.started", **{key: value}) + b"\n")

    snapshot = accumulator.snapshot()

    assert snapshot.status == "invalid"
    assert snapshot.error is not None
    assert snapshot.error["type"] == "provider_session_transport_error"


@pytest.mark.parametrize(
    "payload,finalize",
    (
        (b"\xff\n", False),
        (b'{"type":\n', False),
        (b"[]\n", False),
        (b'{"type":', True),
    ),
)
def test_codex_jsonl_rejects_malformed_transport(
    payload: bytes,
    finalize: bool,
):
    accumulator = _new_accumulator()
    accumulator.feed(payload)
    if finalize:
        accumulator.finalize(expected_session_id=None, require_terminal=False)

    snapshot = accumulator.snapshot()

    assert snapshot.status == "invalid"
    assert snapshot.error is not None
    assert snapshot.error["type"] == "provider_session_transport_error"


def test_codex_jsonl_invalid_stream_discards_unterminated_valid_tail():
    emitted: list[str] = []
    accumulator = _new_accumulator(assistant_text_callback=emitted.append)
    valid_tail = _jsonl_event(
        type="item.completed",
        session_id="late-session",
        item={"type": "agent_message", "text": "late text"},
    )
    accumulator.feed(b'{"type":\n' + valid_tail)
    before = accumulator.snapshot()

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )
    after = accumulator.snapshot()

    assert before.status == "invalid"
    assert before.session_ids == ()
    assert before.terminal_seen is False
    assert accumulator.event_count == 1
    assert after == before
    assert emitted == []
    assert metadata is None
    assert error is not None
    assert error["type"] == "provider_session_transport_error"


def test_codex_jsonl_nested_agent_item_contributes_text_without_terminal():
    emitted: list[str] = []
    accumulator = _new_accumulator(assistant_text_callback=emitted.append)
    accumulator.feed(
        _jsonl_event(
            type="item.completed",
            item={"type": "agent_message", "text": "nested text"},
        )
        + b"\n"
    )

    snapshot = accumulator.snapshot()
    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    assert snapshot.terminal_seen is False
    assert emitted == ["nested text"]
    assert metadata is None
    assert error is not None
    assert "did not expose" in error["message"]


def test_codex_jsonl_rejects_lone_surrogate_assistant_text():
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-surrogate")
        + b"\n"
    )
    accumulator.feed(
        b'{"type":"item.completed","item":'
        b'{"type":"agent_message","text":"\\ud800"}}\n'
    )
    accumulator.feed(_jsonl_event(type="turn.completed") + b"\n")

    snapshot = accumulator.snapshot()
    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=True,
    )

    assert snapshot.status == "invalid"
    assert metadata is None
    assert error is not None
    assert error["type"] == "provider_session_transport_error"
    assert "unicode" in error["message"].lower()


@pytest.mark.parametrize("terminal_type", ("turn.completed", "response.completed"))
def test_codex_jsonl_accepts_only_exact_supported_terminal_types(terminal_type: str):
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    accumulator.feed(_jsonl_event(type=terminal_type) + b"\n")

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=True,
    )

    assert error is None
    assert metadata is not None
    assert accumulator.snapshot().terminal_seen is True


@pytest.mark.parametrize(
    "lookalike",
    (
        {"type": "item.completed"},
        {"type": "turn.part.completed"},
        {"type": "completed"},
        {"type": "done"},
        {"type": "response.done"},
        {"type": "turn.started", "status": "completed"},
    ),
)
def test_codex_jsonl_rejects_terminal_suffix_status_and_generic_lookalikes(
    lookalike: dict[str, Any],
):
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    accumulator.feed(_jsonl_event(**lookalike) + b"\n")

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=True,
    )

    assert accumulator.snapshot().terminal_seen is False
    assert metadata is None
    assert error is not None
    assert error["type"] == "provider_session_transport_error"
    assert "terminal" in error["message"].lower()


@pytest.mark.parametrize("non_string_type", ([], {}), ids=("list", "object"))
def test_codex_jsonl_non_string_event_type_is_not_terminal_on_feed(
    non_string_type: Any,
):
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )

    accumulator.feed(_jsonl_event(type=non_string_type) + b"\n")
    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    assert error is None
    assert metadata is not None
    assert accumulator.snapshot().terminal_seen is False


@pytest.mark.parametrize("non_string_type", ([], {}), ids=("list", "object"))
def test_codex_jsonl_non_string_event_type_is_not_terminal_at_eof(
    non_string_type: Any,
):
    accumulator = _new_accumulator()
    accumulator.feed(
        _jsonl_event(type="thread.started", thread_id="thread-one") + b"\n"
    )
    accumulator.feed(_jsonl_event(type=non_string_type))

    metadata, error = accumulator.finalize(
        expected_session_id=None,
        require_terminal=False,
    )

    assert error is None
    assert metadata is not None
    assert accumulator.snapshot().terminal_seen is False


def test_codex_jsonl_rejects_requested_session_identity_mismatch():
    accumulator = _new_accumulator()
    accumulator.feed(
        b"\n".join(
            (
                _jsonl_event(type="thread.started", thread_id="thread-observed"),
                _jsonl_event(type="turn.completed"),
            )
        )
        + b"\n"
    )

    metadata, error = accumulator.finalize(
        expected_session_id="thread-requested",
        require_terminal=True,
    )

    assert metadata is None
    assert error is not None
    assert error["context"] == {
        "expected_session_id": "thread-requested",
        "observed_session_id": "thread-observed",
    }


def test_session_transport_factory_selects_codec_by_metadata_mode():
    module = _session_transport_module()

    accumulator = module.create_session_transport_accumulator(
        ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
    )

    assert isinstance(accumulator, module.CodexExecJsonlAccumulator)
    assert module.create_session_transport_accumulator("unsupported-mode") is None


def test_session_transport_codec_is_exported_from_provider_package():
    module = _session_transport_module()

    assert provider_api.SessionIdentitySnapshot is module.SessionIdentitySnapshot
    assert (
        provider_api.CodexExecJsonlAccumulator
        is module.CodexExecJsonlAccumulator
    )


def test_session_callback_feeds_accumulator_when_streaming_is_disabled(
    tmp_path: Path,
):
    accumulator = _new_accumulator()
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation = ProviderInvocation(
        command=["unused"],
        input_mode=InputMode.STDIN,
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )
    callback = executor._build_session_stdout_callback(
        invocation=invocation,
        stream_output=False,
        session_runtime=None,
        accumulator=accumulator,
    )

    callback(
        _jsonl_event(type="thread.started", thread_id="thread-callback") + b"\n"
    )

    assert accumulator.snapshot().session_ids == ("thread-callback",)


def test_session_spool_failure_does_not_block_authoritative_accumulator(
    tmp_path: Path,
):
    raw_stdout = (
        b"\n".join(
            (
                _jsonl_event(type="thread.started", thread_id="thread-spool"),
                _jsonl_event(
                    type="item.completed",
                    item={"type": "agent_message", "text": "still valid"},
                ),
                _jsonl_event(type="turn.completed"),
            )
        )
        + b"\n"
    )
    broken_spool_path = tmp_path / "spool-is-a-directory"
    broken_spool_path.mkdir()
    invocation = ProviderInvocation(
        command=[
            "python",
            "-c",
            "import os; os.write(1, bytes.fromhex(%r))" % raw_stdout.hex(),
        ],
        input_mode=InputMode.STDIN,
        prompt="Test prompt",
        command_variant="fresh_command",
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(
        invocation,
        stream_output=False,
        session_runtime={"transport_spool_path": broken_spool_path},
    )

    assert result.exit_code == 0
    assert result.raw_stdout == raw_stdout
    assert result.stdout == b"still valid"
    assert result.provider_session == {
        "session_id": "thread-spool",
        "normalized_stdout": "still valid",
        "event_count": 3,
    }


@pytest.mark.parametrize("non_string_type", ([], {}), ids=("list", "object"))
def test_session_executor_preserves_raw_eof_for_non_string_event_type(
    tmp_path: Path,
    non_string_type: Any,
):
    raw_stdout = b"\n".join(
        (
            _jsonl_event(type="thread.started", thread_id="thread-eof"),
            _jsonl_event(type=non_string_type),
        )
    )
    invocation = ProviderInvocation(
        command=[
            "python",
            "-c",
            "import os; os.write(1, bytes.fromhex(%r))" % raw_stdout.hex(),
        ],
        input_mode=InputMode.STDIN,
        prompt="Test prompt",
        command_variant="fresh_command",
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(invocation)

    assert result.exit_code == 2
    assert result.raw_stdout == raw_stdout
    assert result.provider_session is None
    assert result.error is not None
    assert result.error["type"] == "provider_session_transport_error"
    assert "terminal" in result.error["message"].lower()


def test_session_executor_rejects_lone_surrogate_and_preserves_raw_stdout(
    tmp_path: Path,
):
    raw_stdout = b"\n".join(
        (
            _jsonl_event(
                type="thread.started",
                thread_id="thread-surrogate",
            ),
            (
                b'{"type":"item.completed","item":'
                b'{"type":"agent_message","text":"\\ud800"}}'
            ),
            _jsonl_event(type="turn.completed"),
        )
    )
    invocation = ProviderInvocation(
        command=[
            "python",
            "-c",
            "import os; os.write(1, bytes.fromhex(%r))" % raw_stdout.hex(),
        ],
        input_mode=InputMode.STDIN,
        prompt="Test prompt",
        command_variant="fresh_command",
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(invocation)

    assert result.exit_code == 2
    assert result.raw_stdout == raw_stdout
    assert result.stdout == b""
    assert result.provider_session is None
    assert result.error is not None
    assert result.error["type"] == "provider_session_transport_error"
    assert "unicode" in result.error["message"].lower()


def test_session_executor_uses_real_codex_shape_and_preserves_raw_stdout(
    tmp_path: Path,
):
    raw_stdout = b"\n".join(
        (
            _jsonl_event(type="thread.started", thread_id="thread-real"),
            _jsonl_event(
                type="item.completed",
                item={"type": "agent_message", "text": "real output"},
            ),
            _jsonl_event(type="turn.completed"),
        )
    )
    invocation = ProviderInvocation(
        command=[
            "python",
            "-c",
            "import os; os.write(1, bytes.fromhex(%r))" % raw_stdout.hex(),
        ],
        input_mode=InputMode.STDIN,
        prompt="Test prompt",
        command_variant="fresh_command",
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(invocation)

    assert result.exit_code == 0
    assert result.raw_stdout == raw_stdout
    assert result.stdout == b"real output"
    assert result.provider_session == {
        "session_id": "thread-real",
        "normalized_stdout": "real output",
        "event_count": 3,
    }


def test_legacy_codex_jsonl_parser_delegates_to_shared_real_shape_codec(
    tmp_path: Path,
):
    raw_stdout = b"\n".join(
        (
            _jsonl_event(type="thread.started", thread_id="thread-real"),
            _jsonl_event(
                type="item.completed",
                item={"type": "agent_message", "text": "delegated"},
            ),
            _jsonl_event(type="turn.completed"),
        )
    )

    metadata, error = ProviderExecutor(
        tmp_path,
        ProviderRegistry(),
    )._parse_codex_jsonl_transport(raw_stdout)

    assert error is None
    assert metadata == {
        "session_id": "thread-real",
        "normalized_stdout": "delegated",
        "event_count": 3,
    }
