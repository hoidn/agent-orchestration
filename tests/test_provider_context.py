"""Contract tests for the closed portable provider-context value."""

from __future__ import annotations

import pytest

from orchestrator.providers.portable_context import validate_portable_context_v1
from orchestrator.workflow.type_descriptor import MAX_TRANSPORT_VALUE_BYTES


def _origin() -> dict[str, str]:
    return {"variant": "CAPTURED", "provider": "codex", "attempt": "run/step/1"}


def _context() -> dict[str, object]:
    origin = _origin()
    return {
        "schema": "portable-context.v1",
        "events": [
            {"variant": "TASK", "origin": origin, "sequence": 0, "text": "inspect marker"},
            {
                "variant": "COMMAND",
                "origin": origin,
                "call_sequence": 1,
                "result_sequence": 2,
                "item_id": "cmd-1",
                "command": "cat marker",
                "output": "marker-value",
                "exit_code": 0,
            },
            {
                "variant": "ASSISTANT",
                "origin": origin,
                "sequence": 3,
                "item_id": "msg-1",
                "text": "marker found",
            },
        ],
        "coverage": [
            {
                "origin": origin,
                "scope": "codex-exec-jsonl",
                "retained_kinds": ["TASK", "ASSISTANT", "COMMAND"],
                "omitted_kinds": ["REASONING"],
                "conversions": [],
            }
        ],
        "lineage": [],
    }


def test_portable_context_v1_validates_closed_command_trace() -> None:
    context = _context()

    assert validate_portable_context_v1(context) == context


def test_portable_context_v1_keeps_file_change_metadata_without_patch_content() -> None:
    context = _context()
    origin = _origin()
    context["events"].extend(
        (
            {
                "variant": "FILE_CHANGE",
                "origin": origin,
                "sequence": 4,
                "item_id": "change-1",
                "status": "completed",
                "changes": [
                    {"path": "src/a.py", "kind": "update"},
                    {"path": "src/new.py", "kind": "add"},
                ],
            },
            {
                "variant": "FILE_CHANGE",
                "origin": origin,
                "sequence": 5,
                "item_id": "change-2",
                "status": "failed",
                "changes": [],
            },
        )
    )
    context["coverage"][0]["retained_kinds"].append("FILE_CHANGE")
    context["coverage"][0]["conversions"].append(
        "codex-file-change-metadata-only"
    )

    assert validate_portable_context_v1(context) == context


@pytest.mark.parametrize(
    "mutate",
    [
        lambda event: event.update(status="in_progress"),
        lambda event: event["changes"][0].update(kind="rename"),
    ],
)
def test_portable_context_v1_rejects_nonterminal_or_unknown_file_change_metadata(mutate) -> None:
    context = _context()
    context["events"].append(
        {
            "variant": "FILE_CHANGE",
            "origin": _origin(),
            "sequence": 4,
            "item_id": "change-1",
            "status": "completed",
            "changes": [{"path": "src/a.py", "kind": "update"}],
        }
    )
    context["coverage"][0]["retained_kinds"].append("FILE_CHANGE")
    mutate(context["events"][-1])

    with pytest.raises(ValueError, match="file change"):
        validate_portable_context_v1(context)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["events"][1].update(result_sequence=1),
        lambda value: value["events"][2].update(item_id="cmd-1"),
        lambda value: value["coverage"][0]["origin"].update(provider=""),
        lambda value: value["coverage"].__setitem__(
            0,
            {
                **value["coverage"][0],
                "origin": {"variant": "AUTHORED", "label": "wrong"},
            },
        ),
    ],
)
def test_portable_context_v1_rejects_invalid_event_relationships(mutate) -> None:
    context = _context()
    mutate(context)

    with pytest.raises(ValueError):
        validate_portable_context_v1(context)


def test_portable_context_v1_requires_coverage_for_retained_event_kinds() -> None:
    context = _context()
    context["coverage"][0]["retained_kinds"] = ["TASK", "ASSISTANT"]

    with pytest.raises(ValueError, match="coverage"):
        validate_portable_context_v1(context)


def test_portable_context_v1_keeps_coverage_when_selection_removes_events() -> None:
    context = _context()
    context["events"] = []
    context["coverage"][0].update(
        retained_kinds=[],
        omitted_kinds=["TASK", "ASSISTANT", "COMMAND", "REASONING"],
    )

    assert validate_portable_context_v1(context) == context


def test_portable_context_v1_allows_authored_reordered_presentation() -> None:
    authored = {"variant": "AUTHORED", "label": "\u03bb notes"}
    context = {
        "schema": "portable-context.v1",
        "events": [
            {
                "variant": "ASSISTANT",
                "origin": authored,
                "sequence": 2,
                "item_id": "answer",
                "text": "\u03bb",
            },
            {
                "variant": "TASK",
                "origin": authored,
                "sequence": 0,
                "text": "question",
            },
        ],
        "coverage": [
            {
                "origin": authored,
                "scope": "authored-selection",
                "retained_kinds": ["TASK", "ASSISTANT"],
                "omitted_kinds": [],
                "conversions": [],
            }
        ],
        "lineage": [
            {
                "sources": [],
                "operation": "reorder",
                "loss": [],
            }
        ],
    }

    assert validate_portable_context_v1(context) == context


def test_portable_context_v1_rejects_contradictory_coverage_and_unknown_fields() -> None:
    context = _context()
    context["coverage"][0]["omitted_kinds"] = ["COMMAND"]
    with pytest.raises(ValueError, match="coverage"):
        validate_portable_context_v1(context)

    context = _context()
    context["events"][0]["extra"] = "not closed"
    with pytest.raises(ValueError, match="extra"):
        validate_portable_context_v1(context)


def test_portable_context_v1_uses_transport_size_limit() -> None:
    context = _context()
    context["events"][0]["text"] = "x" * MAX_TRANSPORT_VALUE_BYTES

    with pytest.raises(ValueError, match="byte limit"):
        validate_portable_context_v1(context)
