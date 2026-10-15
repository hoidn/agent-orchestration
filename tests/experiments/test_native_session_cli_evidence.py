from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.mark.parametrize("closed_before_second", [True, False])
def test_claude_overlap_respects_native_structured_output_terminal(closed_before_second: bool, tmp_path: Path) -> None:
    rows = [
        {"type": "user", "uuid": "user-a", "parentUuid": None, "sessionId": "session-a", "promptId": "prompt-a", "message": {"role": "user", "content": "nonce-one"}},
        {"type": "assistant", "uuid": "assistant-a", "parentUuid": "user-a", "sessionId": "session-a", "message": {"content": [{"type": "tool_use", "id": "tool-a", "name": "StructuredOutput", "input": {"nonce": "nonce-one"}}], "stop_reason": "tool_use"}},
        {"type": "attachment", "uuid": "structured-a", "parentUuid": "assistant-a", "sessionId": "session-a", "attachment": {"type": "structured_output", "toolUseID": "tool-a", "data": {"nonce": "nonce-one"}}},
        {"type": "user", "uuid": "completion-a", "parentUuid": "assistant-a", "sessionId": "session-a", "promptId": "prompt-a", "sourceToolAssistantUUID": "assistant-a", "toolEndsTurn": True, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tool-a", "content": "successful"}]}},
    ]
    second = {"type": "user", "uuid": "user-b", "parentUuid": "completion-a" if closed_before_second else "user-a", "sessionId": "session-a", "promptId": "prompt-b", "message": {"role": "user", "content": "nonce-two"}}
    rows.insert(4 if closed_before_second else 1, second)
    path = tmp_path / "overlap.jsonl"
    _write_jsonl(path, rows)
    module = _evidence_module()
    first = module.inspect_native_user_turn("claude", path, nonce="nonce-one", expected_session="session-a")
    second = module.inspect_native_user_turn("claude", path, nonce="nonce-two", expected_session="session-a")
    assert module.native_turn_open_at_append("claude", path, first, second) is (not closed_before_second)


@pytest.mark.parametrize("mutation", [None, "missing-marker", "wrong-source", "wrong-tool", "wrong-data", "wrong-data-type", "missing-attachment", "wrong-session", "sidechain", "error", "later-head", "bad-parent", "wrong-prompt", "duplicate-close", "continued-turn", "continued-padding", "padding-model", "padding-usage", "padding-parent", "padding-error", "padding-content"])
def test_claude_structured_output_binds_native_attachment_and_terminal_tool_result(tmp_path: Path, mutation: str | None) -> None:
    result = {"schema": 1, "nonce": "nonce-one", "reviewed": True}
    rows = [
        {"type": "user", "uuid": "user-a", "parentUuid": None, "sessionId": "session-a", "promptId": "prompt-a", "message": {"role": "user", "content": "nonce-one"}},
        {"type": "attachment", "uuid": "environment-a", "parentUuid": "user-a", "sessionId": "session-a", "isSidechain": False, "attachment": {"type": "environment"}},
        {"type": "assistant", "uuid": "assistant-a", "parentUuid": "environment-a", "sessionId": "session-a", "message": {"role": "assistant", "stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "tool-a", "name": "StructuredOutput", "input": dict(result)}]}},
        {"type": "attachment", "uuid": "structured-a", "parentUuid": "assistant-a", "sessionId": "session-a", "attachment": {"type": "structured_output", "toolUseID": "tool-a", "data": dict(result)}},
        {"type": "user", "uuid": "completion-a", "parentUuid": "assistant-a", "sessionId": "session-a", "promptId": "prompt-a", "sourceToolAssistantUUID": "assistant-a", "toolEndsTurn": True, "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tool-a", "content": "Structured output provided successfully"}]}},
    ]
    if mutation == "missing-marker":
        rows[-1].pop("toolEndsTurn")
    elif mutation == "wrong-source":
        rows[-1]["sourceToolAssistantUUID"] = "other-assistant"
    elif mutation == "wrong-tool":
        rows[-1]["message"]["content"][0]["tool_use_id"] = "other-tool"
    elif mutation == "wrong-data":
        rows[-2]["attachment"]["data"]["nonce"] = "stale-nonce"
    elif mutation == "wrong-data-type":
        rows[-2]["attachment"]["data"]["schema"] = True
    elif mutation == "missing-attachment":
        rows.pop(-2)
    elif mutation == "wrong-session":
        rows[1]["sessionId"] = "other-session"
    elif mutation == "sidechain":
        rows[1]["isSidechain"] = True
    elif mutation == "error":
        rows[-1]["message"]["content"][0]["is_error"] = True
    elif mutation == "later-head":
        rows.append({"type": "assistant", "uuid": "later-a", "parentUuid": "completion-a", "sessionId": "session-a", "message": {"content": [], "stop_reason": "tool_use"}})
    elif mutation == "bad-parent":
        rows[1]["parentUuid"] = "missing-user"
    elif mutation == "wrong-prompt":
        rows[1]["promptId"] = "other-prompt"
    elif mutation == "duplicate-close":
        rows.append({**rows[-1], "uuid": "completion-b"})
    elif mutation == "continued-turn" or mutation == "continued-padding" or (mutation or "").startswith("padding-"):
        previous = json.loads(json.dumps(rows))
        for row in previous:
            row["uuid"] = row["uuid"].replace("-a", "-prev")
            if row.get("parentUuid"):
                row["parentUuid"] = row["parentUuid"].replace("-a", "-prev")
            if "promptId" in row:
                row["promptId"] = "prompt-prev"
            if "sourceToolAssistantUUID" in row:
                row["sourceToolAssistantUUID"] = "assistant-prev"
        previous[0]["message"]["content"] = "nonce-prev"
        previous[2]["message"]["content"][0]["input"]["nonce"] = "nonce-prev"
        previous[3]["attachment"]["data"]["nonce"] = "nonce-prev"
        rows[0]["parentUuid"] = "completion-prev"
        if mutation != "continued-turn":
            padding = {"type": "assistant", "uuid": "padding-prev", "parentUuid": "completion-prev", "sessionId": "session-a", "isSidechain": False, "isApiErrorMessage": False, "message": {"id": "synthetic-message", "model": "<synthetic>", "role": "assistant", "type": "message", "stop_reason": "stop_sequence", "stop_sequence": "", "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, "content": [{"type": "text", "text": "No response requested."}]}}
            if mutation == "padding-model":
                padding["message"]["model"] = "provider-model"
            elif mutation == "padding-usage":
                padding["message"]["usage"]["output_tokens"] = 1
            elif mutation == "padding-parent":
                padding["parentUuid"] = "assistant-prev"
            elif mutation == "padding-error":
                padding["isApiErrorMessage"] = True
            elif mutation == "padding-content":
                padding["message"]["content"][0]["text"] = "An unrelated provider response."
            previous.append(padding)
            rows[0]["parentUuid"] = "padding-prev"
        rows = previous + rows
    path = tmp_path / "native.jsonl"
    _write_jsonl(path, rows)
    continued = mutation in {"continued-turn", "continued-padding"} or (mutation or "").startswith("padding-")
    evidence = _evidence_module().inspect_claude_turn(path, nonce="nonce-one", expected_session="session-a", predecessor_turn="prompt-prev" if continued else None)
    assert evidence.status == ("OBSERVED" if mutation in {None, "continued-turn", "continued-padding"} else "INCONCLUSIVE")
    if mutation in {None, "continued-turn", "continued-padding"}:
        assert evidence.result == result
        assert evidence.turn_id == "prompt-a"
        assert any("completion-a" in ref and "toolEndsTurn" in ref for ref in evidence.refs)

ROOT = Path(__file__).resolve().parents[2]


def _codex_records(
    *,
    nonce: str = "nonce-one",
    session: str = "session-a",
    turn: str = "turn-a",
    completed_turn: str | None = None,
    include_ids: bool = True,
    result_nonce: str | None = None,
    predecessor: str | None = None,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = [
        {"type": "session_meta", "payload": {"id": session}},
    ]
    if predecessor is not None:
        records.extend(
            [
                {"type": "event_msg", "payload": {"type": "task_started", "turn_id": predecessor}},
                {
                    "type": "event_msg",
                    "payload": {"type": "task_complete", "turn_id": predecessor, "last_agent_message": '{"nonce":"previous"}'},
                },
            ]
        )
    records.extend(
        [
            {
                "type": "event_msg",
                "payload": {"type": "task_started", "turn_id": turn if include_ids else None},
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "thread_id": session,
                    "turn_id": turn if include_ids else None,
                    "item": {
                        "id": "user-item",
                        "type": "UserMessage",
                        "content": [{"type": "text", "text": nonce, "text_elements": []}],
                    },
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "item_completed",
                    "thread_id": session,
                    "turn_id": turn if include_ids else None,
                    "item": {
                        "id": "assistant-item",
                        "type": "AgentMessage",
                        "phase": "final_answer",
                        "content": [{"type": "Text", "text": json.dumps({"schema": 2, "nonce": result_nonce or nonce})}],
                    },
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "turn_id": completed_turn if completed_turn is not None else (turn if include_ids else None),
                    "last_agent_message": json.dumps({"schema": 2, "nonce": result_nonce or nonce}),
                },
            },
        ]
    )
    return records


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _evidence_module() -> ModuleType:
    module_path = ROOT / "scripts/experiments/native_session_cli_evidence.py"
    spec = importlib.util.spec_from_file_location("native_session_cli_evidence_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_codex_native_evidence_binds_nonce_session_turn_and_completion(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "session.jsonl", _codex_records(predecessor="turn-prev"))

    module = _evidence_module()
    evidence = module.inspect_codex_turn(
        tmp_path / "session.jsonl",
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn="turn-prev",
    )

    assert evidence.status == "OBSERVED"
    assert evidence.turn_id == "turn-a"
    assert evidence.predecessor_turn_id == "turn-prev"
    assert evidence.raw_sha256.startswith("sha256:")
    assert evidence.refs


@pytest.mark.parametrize(
    "records,tail",
    [
        (_codex_records(completed_turn="other-turn"), ""),
        (_codex_records(result_nonce="stale-nonce"), ""),
        (_codex_records(include_ids=False), ""),
        (_codex_records(), '{"type":"event_msg"'),
    ],
)
def test_codex_native_evidence_fails_closed_on_wrong_or_partial_binding(
    tmp_path: Path,
    records: list[dict[str, object]],
    tail: str,
) -> None:
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, records)
    if tail:
        path.write_text(path.read_text(encoding="utf-8") + tail, encoding="utf-8")

    module = _evidence_module()
    evidence = module.inspect_codex_turn(
        path,
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn=None,
    )

    assert evidence.status == "INCONCLUSIVE"


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_native_append_identity_is_absent_when_native_ids_are_duplicated(tmp_path: Path, provider: str) -> None:
    rows = _codex_records() if provider == "codex" else _claude_records()
    if provider == "codex":
        rows[3]["payload"]["item"]["id"] = rows[2]["payload"]["item"]["id"]
    else:
        rows[1]["uuid"] = rows[0]["uuid"]
    path = tmp_path / "native.jsonl"
    _write_jsonl(path, rows)
    evidence = _evidence_module().inspect_native_user_turn(provider, path, nonce="nonce-one", expected_session="session-a")
    assert evidence.status == "INCONCLUSIVE"
    assert evidence.turn_id is None
    assert evidence.raw_sha256 == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("mutation", ["competing-start", "later-incomplete", "malformed-envelope"])
def test_codex_native_evidence_rejects_competing_or_malformed_head(
    tmp_path: Path,
    mutation: str,
) -> None:
    records = _codex_records()
    if mutation == "competing-start":
        records.insert(
            3,
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-other"}},
        )
    elif mutation == "later-incomplete":
        records.append(
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-other"}}
        )
    else:
        records.append({"type": "event_msg", "payload": []})
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, records)

    evidence = _evidence_module().inspect_codex_turn(
        path,
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn=None,
    )

    assert evidence.status == "INCONCLUSIVE"


def test_native_user_observation_records_append_attempt_without_claiming_completion(
    tmp_path: Path,
) -> None:
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, _codex_records())

    evidence = _evidence_module().inspect_native_user_turn(
        "codex",
        path,
        nonce="nonce-one",
        expected_session="session-a",
    )

    assert evidence.status == "INCONCLUSIVE"
    assert evidence.turn_id == "turn-a"
    assert "completion" in evidence.reason
    assert evidence.refs


def _claude_records(
    *,
    nonce: str = "nonce-one",
    session: str = "session-a",
    prompt: str = "prompt-a",
    result_nonce: str | None = None,
    final_parent: str | None = None,
    include_prompt: bool = True,
    structured_tool: bool = False,
    user_parent: str | None = None,
) -> list[dict[str, object]]:
    user_id = "user-a"
    content: list[dict[str, object]] = (
        [{"type": "tool_use", "name": "StructuredOutput", "input": {"nonce": nonce}}]
        if structured_tool
        else [{"type": "text", "text": json.dumps({"schema": 2, "nonce": result_nonce or nonce})}]
    )
    rows: list[dict[str, object]] = [
        {
            "type": "user",
            "uuid": user_id,
            "parentUuid": user_parent,
            "sessionId": session,
            "promptId": prompt if include_prompt else None,
            "message": {"content": [{"type": "text", "text": nonce}]},
        },
        {
            "type": "assistant",
            "uuid": "assistant-a",
            "parentUuid": final_parent or user_id,
            "sessionId": session,
            "message": {"content": content, "stop_reason": "end_turn"},
        },
    ]
    return rows


def test_claude_native_evidence_requires_parent_lineage_to_nonce_and_end_marker(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, _claude_records())

    evidence = _evidence_module().inspect_claude_turn(
        path,
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn=None,
    )

    assert evidence.status == "OBSERVED"
    assert evidence.turn_id == "prompt-a"
    assert evidence.raw_sha256.startswith("sha256:")


@pytest.mark.parametrize(
    "records",
    [
        _claude_records(final_parent="unrelated-message"),
        _claude_records(result_nonce="stale-nonce"),
        _claude_records(include_prompt=False),
        _claude_records(structured_tool=True),
        _claude_records(session="another-session"),
    ],
)
def test_claude_native_evidence_fails_closed_on_unsupported_or_misbound_records(
    tmp_path: Path,
    records: list[dict[str, object]],
) -> None:
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, records)

    evidence = _evidence_module().inspect_claude_turn(
        path,
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn=None,
    )

    assert evidence.status == "INCONCLUSIVE"


def _claude_with_predecessor(*, previous_complete_after_target: bool = False) -> list[dict[str, object]]:
    previous_user = {
        "type": "user",
        "uuid": "user-prev",
        "parentUuid": None,
        "sessionId": "session-a",
        "promptId": "prompt-prev",
        "message": {"content": [{"type": "text", "text": "old turn"}]},
    }
    previous_assistant = {
        "type": "assistant",
        "uuid": "assistant-prev",
        "parentUuid": "user-prev",
        "sessionId": "session-a",
        "message": {"content": [{"type": "text", "text": "old result"}], "stop_reason": "end_turn"},
    }
    current = _claude_records(user_parent="assistant-prev")
    if previous_complete_after_target:
        return [previous_user, current[0], previous_assistant, current[1]]
    return [previous_user, previous_assistant, *current]


def test_claude_native_evidence_binds_expected_predecessor_to_current_user(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, _claude_with_predecessor())

    evidence = _evidence_module().inspect_claude_turn(
        path,
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn="prompt-prev",
    )

    assert evidence.status == "OBSERVED"
    assert evidence.predecessor_turn_id == "prompt-prev"


@pytest.mark.parametrize("mutation", ["missing-parent", "late-predecessor", "foreign-bridge", "intervening-user"])
def test_claude_native_evidence_rejects_broken_predecessor_or_ancestry(
    tmp_path: Path,
    mutation: str,
) -> None:
    rows = _claude_with_predecessor(previous_complete_after_target=mutation == "late-predecessor")
    current_user_index = 1 if mutation == "late-predecessor" else 2
    current_final_index = len(rows) - 1
    if mutation == "missing-parent":
        rows[current_user_index]["parentUuid"] = "does-not-exist"
    elif mutation == "foreign-bridge":
        bridge = {
            "type": "assistant",
            "uuid": "foreign-bridge",
            "parentUuid": "user-a",
            "sessionId": "foreign-session",
            "promptId": "foreign-prompt",
            "message": {"content": [{"type": "text", "text": "bridge"}]},
        }
        rows.insert(current_final_index, bridge)
        rows[-1]["parentUuid"] = "foreign-bridge"
    elif mutation == "intervening-user":
        bridge = {
            "type": "user",
            "uuid": "other-user",
            "parentUuid": "user-a",
            "sessionId": "session-a",
            "promptId": "other-prompt",
            "message": {"content": [{"type": "text", "text": "another prompt"}]},
        }
        rows.insert(current_final_index, bridge)
        rows[-1]["parentUuid"] = "other-user"
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, rows)

    evidence = _evidence_module().inspect_claude_turn(
        path,
        nonce="nonce-one",
        expected_session="session-a",
        predecessor_turn="prompt-prev",
    )

    assert evidence.status == "INCONCLUSIVE"


@pytest.mark.parametrize("mutation", ["guessed-user-block", "guessed-final-block", "guessed-phase", "empty-turn", "empty-session", "trailing-item", "duplicate-user", "shared-item-id", "second-user"])
def test_codex_rejects_unsupported_or_ambiguous_native_shape(tmp_path: Path, mutation: str) -> None:
    rows = _codex_records()
    if mutation == "guessed-user-block":
        rows[2]["payload"]["item"]["content"][0]["type"] = "input_text"
    elif mutation == "guessed-final-block":
        rows[3]["payload"]["item"]["content"][0]["type"] = "output_text"
    elif mutation == "guessed-phase":
        rows[3]["payload"]["item"]["phase"] = "final"
    elif mutation == "empty-turn":
        rows = _codex_records(turn="")
    elif mutation == "empty-session":
        rows = _codex_records(session="")
    elif mutation == "trailing-item":
        rows.append(rows[3].copy())
    elif mutation == "shared-item-id":
        rows[3]["payload"]["item"]["id"] = rows[2]["payload"]["item"]["id"]
    elif mutation == "second-user":
        other = json.loads(json.dumps(rows[2]))
        other["payload"]["item"].update(id="other-user", content=[{"type": "text", "text": "another input", "text_elements": []}])
        rows.insert(3, other)
    else:
        rows.insert(3, rows[2].copy())
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, rows)
    evidence = _evidence_module().inspect_codex_turn(
        path, nonce="nonce-one", expected_session=None, predecessor_turn=None
    )
    assert evidence.status == "INCONCLUSIVE"


@pytest.mark.parametrize("mutation", ["completion-before-start", "restarted-predecessor", "duplicate-cycle"])
def test_codex_rejects_invalid_preceding_lifecycle(tmp_path: Path, mutation: str) -> None:
    rows = _codex_records(predecessor="turn-prev")
    if mutation == "completion-before-start":
        rows[1], rows[2] = rows[2], rows[1]
    elif mutation == "restarted-predecessor":
        rows.insert(3, rows[1].copy())
    else:
        rows[3:3] = [rows[1].copy(), rows[2].copy()]
    path = tmp_path / "session.jsonl"
    _write_jsonl(path, rows)
    evidence = _evidence_module().inspect_codex_turn(
        path, nonce="nonce-one", expected_session="session-a", predecessor_turn="turn-prev"
    )
    assert evidence.status == "INCONCLUSIVE"


@pytest.mark.parametrize("mutation", ["future-parent", "missing-final-id", "empty-final-id", "late-ancestor"])
def test_claude_rejects_unordered_or_unidentified_ancestry(tmp_path: Path, mutation: str) -> None:
    rows = _claude_records()
    if mutation in {"future-parent", "late-ancestor"}:
        bridge = dict(rows[1], uuid="bridge", parentUuid="user-a", message={"content": []})
        rows[1]["parentUuid"] = "bridge"
        if mutation == "late-ancestor":
            later = dict(bridge, uuid="later")
            bridge["parentUuid"] = "later"
            rows.insert(1, bridge)
            rows.append(later)
        else:
            rows.append(bridge)
    elif mutation == "missing-final-id":
        rows[1].pop("uuid")
    else:
        rows[1]["uuid"] = ""
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, rows)
    evidence = _evidence_module().inspect_claude_turn(
        path, nonce="nonce-one", expected_session="session-a", predecessor_turn=None
    )
    assert evidence.status == "INCONCLUSIVE"


@pytest.mark.parametrize("mutation", [None, "foreign-prompt", "foreign-session", "late-result", "conflicting-final-prompt", "trailing-append", "orphan-before-user"])
def test_claude_tool_result_lineage_uses_native_user_prompt(tmp_path: Path, mutation: str | None) -> None:
    rows = _claude_records()
    rows[0]["message"]["content"] = "nonce-one"
    tool = dict(rows[1], uuid="tool-assistant", parentUuid="user-a", message={
        "content": [{"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {}}], "stop_reason": "tool_use"
    })
    response = dict(rows[0], uuid="tool-response", parentUuid="tool-assistant", message={
        "role": "user", "content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": "nonce-one"}]
    })
    rows[1]["parentUuid"] = "tool-response"
    rows[1:1] = [tool, response]
    if mutation == "foreign-prompt":
        response["promptId"] = "other-prompt"
    elif mutation == "foreign-session":
        response["sessionId"] = "other-session"
    elif mutation == "late-result":
        rows[2], rows[3] = rows[3], rows[2]
    elif mutation == "conflicting-final-prompt":
        rows[-1]["promptId"] = "other-prompt"
    elif mutation == "trailing-append":
        rows.append(dict(tool, uuid="trailing", parentUuid="assistant-a"))
    elif mutation == "orphan-before-user":
        rows.insert(0, dict(tool, uuid="orphan", parentUuid=None))
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, rows)
    evidence = _evidence_module().inspect_claude_turn(
        path, nonce="nonce-one", expected_session="session-a", predecessor_turn=None
    )
    assert evidence.status == ("OBSERVED" if mutation is None else "INCONCLUSIVE")


@pytest.mark.parametrize("provider", ["codex", "claude"])
@pytest.mark.parametrize("mutation", ["nonce-prefix", "duplicate-json-key", "nonfinite-json", "overflow-json"])
def test_native_parser_rejects_ambiguous_nonce_or_json(tmp_path: Path, provider: str, mutation: str) -> None:
    rows = _codex_records() if provider == "codex" else _claude_records()
    user_content = rows[2]["payload"]["item"]["content"] if provider == "codex" else rows[0]["message"]["content"]
    final_content = rows[3]["payload"]["item"]["content"] if provider == "codex" else rows[1]["message"]["content"]
    if mutation == "nonce-prefix":
        user_content[0]["text"] = "nonce-one-suffix"
    else:
        result = {"duplicate-json-key": '{"nonce":"wrong","nonce":"nonce-one"}', "nonfinite-json": '{"nonce":"nonce-one","extra":Infinity}', "overflow-json": '{"nonce":"nonce-one","extra":1e400}'}[mutation]
        final_content[0]["text"] = result
        if provider == "codex":
            rows[-1]["payload"]["last_agent_message"] = result
    path = tmp_path / "native.jsonl"
    _write_jsonl(path, rows)
    evidence = getattr(_evidence_module(), f"inspect_{provider}_turn")(
        path, nonce="nonce-one", expected_session="session-a", predecessor_turn=None
    )
    assert evidence.status == "INCONCLUSIVE"


