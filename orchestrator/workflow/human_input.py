"""Durable host-input request records, without execution dispatch."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from orchestrator._common.canonical import sha256_json as _sha256_json
from orchestrator._common.validation import closed_mapping, nonempty_string
from orchestrator.state import RunState

from .provider_attempts import EnclosingStep, LoopIteration
from .resume_projection_integrity import ResumeScopePath


_PENDING_KEYS = {
    "request_id", "resume_scope", "runtime_step_id", "enclosing_step",
    "loop_iteration", "question", "status",
}
_SETTLED_KEYS = _PENDING_KEYS | {"reply"}
HUMAN_REPLY_VARIANTS = ("ANSWERED", "CANCELLED")




def human_reply_artifact_contracts() -> dict[str, dict[str, Any]]:
    """Return the fixed ordinary union projection for one host reply."""

    common = {
        "projection_class": "union_workflow_boundary",
        "return_kind": "union",
        "union_output_group": "human_reply",
        "discriminant_output": "variant",
    }
    return {
        "variant": {
            "type": "enum",
            "allowed": list(HUMAN_REPLY_VARIANTS),
            "projection": {
                **common,
                "field_role": "discriminant",
                "active_variants": list(HUMAN_REPLY_VARIANTS),
            },
        },
        "text": {
            "type": "string",
            "projection": {
                **common,
                "field_role": "variant",
                "active_variants": ["ANSWERED"],
            },
        },
    }


def human_reply_result_contract_digest() -> str:
    """Return the stable identity of the fixed complete HumanReply contract."""

    return _sha256_json(human_reply_artifact_contracts())


def _scope_from_dict(value: Any) -> ResumeScopePath:
    node = closed_mapping(
        value, {"root_workflow_file", "call_frame_ids"}, "resume_scope"
    )
    return ResumeScopePath(node["root_workflow_file"], node["call_frame_ids"])




def validate_human_reply(value: Any) -> dict[str, Any]:
    """Validate the complete fixed reply before using any of its members."""
    if not isinstance(value, Mapping):
        raise ValueError("human input reply must be an object")
    variant = value.get("variant")
    if variant == "ANSWERED":
        reply = closed_mapping(value, {"variant", "text"}, "human input reply")
        if not isinstance(reply["text"], str):
            raise ValueError("human input answer text must be a string")
        return {"variant": "ANSWERED", "text": reply["text"]}
    if variant == "CANCELLED":
        closed_mapping(value, {"variant"}, "human input reply")
        return {"variant": "CANCELLED"}
    raise ValueError("human input reply variant is invalid")


def _request_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("human input request_id is invalid")
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("human input request_id is invalid") from exc


def validate_human_input_record(value: Any) -> dict[str, Any]:
    """Return a detached canonical record with the status-specific shape."""

    if not isinstance(value, Mapping):
        raise ValueError("human input must be a closed object")
    status = value.get("status")
    keys = _PENDING_KEYS if status == "pending" else _SETTLED_KEYS
    record = closed_mapping(value, keys, "human input")
    if status not in {"pending", "answered", "consumed"}:
        raise ValueError("human input status is invalid")
    request_id = _request_id(record["request_id"])
    scope = _scope_from_dict(record["resume_scope"])
    runtime_step_id = nonempty_string(
        record["runtime_step_id"], "human input runtime_step_id"
    )
    enclosing = EnclosingStep.from_dict(record["enclosing_step"])
    loop_value = record["loop_iteration"]
    loop = None if loop_value is None else LoopIteration.from_dict(loop_value)
    if not isinstance(record["question"], str):
        raise ValueError("human input question must be a string")
    result = {
        "request_id": request_id,
        "resume_scope": {"root_workflow_file": scope.root_workflow_file, "call_frame_ids": list(scope.call_frame_ids)},
        "runtime_step_id": runtime_step_id,
        "enclosing_step": enclosing.to_dict(),
        "loop_iteration": None if loop is None else loop.to_dict(),
        "question": record["question"],
        "status": status,
    }
    if status != "pending":
        result["reply"] = validate_human_reply(record["reply"])
    return result




def get_human_input(run_root: Path | str) -> dict[str, Any] | None:
    """Read the latest detached root request from one persisted run."""

    state_file = Path(run_root) / "state.json"
    state = RunState.from_dict(json.loads(state_file.read_text(encoding="utf-8")))
    return None if state.human_input is None else deepcopy(state.human_input)










__all__ = [
    "HumanInputSuspended", "consume_human_input", "get_human_input", "human_input_reached_position_matches", "record_human_input", "submit_human_input",
    "validate_human_input_record",
]
