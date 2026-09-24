"""Durable host-input request records, without execution dispatch."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from orchestrator._common.canonical import sha256_json as _sha256_json
from orchestrator._common.validation import closed_mapping, nonempty_string
from orchestrator.run_lock import run_writer_lock
from orchestrator.state import RunState, StateManager, StepResult, _apply_result_with_dataflow

from .provider_attempts import EnclosingStep, LoopIteration, resolve_aggregate_run_owner
from .resume_projection_integrity import ResumeScopePath
from .state_projection import IterationStepKeyProjection


_PENDING_KEYS = {
    "request_id", "resume_scope", "runtime_step_id", "enclosing_step",
    "loop_iteration", "question", "status",
}
_SETTLED_KEYS = _PENDING_KEYS | {"reply"}
HUMAN_REPLY_VARIANTS = ("ANSWERED", "CANCELLED")


class HumanInputSuspended(Exception):
    """Control transfer raised after a request has been durably recorded."""


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


def _scope_to_dict(scope: ResumeScopePath) -> dict[str, Any]:
    return {
        "root_workflow_file": scope.root_workflow_file,
        "call_frame_ids": list(scope.call_frame_ids),
    }


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
        "resume_scope": _scope_to_dict(scope),
        "runtime_step_id": runtime_step_id,
        "enclosing_step": enclosing.to_dict(),
        "loop_iteration": None if loop is None else loop.to_dict(),
        "question": record["question"],
        "status": status,
    }
    if status != "pending":
        result["reply"] = validate_human_reply(record["reply"])
    return result


def human_input_reached_position_matches(
    leaf: RunState,
    *,
    runtime_step_id: str,
    enclosing: EnclosingStep,
    loop: LoopIteration | None,
) -> bool:
    current = leaf.current_step
    current_matches = (
        leaf.status in {"running", "suspended"}
        and isinstance(current, Mapping)
        and current.get("step_id") == enclosing.step_id
        and current.get("name") == enclosing.step_name
        and current.get("visit_count") == enclosing.visit_count
    )
    recorded_visit = leaf.step_visits.get(enclosing.step_name)
    visit_matches = (
        isinstance(recorded_visit, int)
        and not isinstance(recorded_visit, bool)
        and recorded_visit == enclosing.visit_count
    )
    if loop is None:
        return current_matches and visit_matches and runtime_step_id == enclosing.step_id
    runtime_matches = (
        loop.loop_step_id == enclosing.step_id
        and runtime_step_id.startswith(f"{loop.loop_step_id}#{loop.iteration}.")
        and len(runtime_step_id) > len(f"{loop.loop_step_id}#{loop.iteration}.")
    )
    if loop.kind == "for_each":
        progress = leaf.for_each.get(enclosing.step_name)
        current_index = getattr(progress, "current_index", None)
        progress_matches = (
            isinstance(current_index, int)
            and not isinstance(current_index, bool)
            and current_index == loop.iteration
        )
    else:
        progress = leaf.repeat_until.get(enclosing.step_name)
        progress_matches = (
            isinstance(progress, Mapping)
            and isinstance(progress.get("current_iteration"), int)
            and not isinstance(progress.get("current_iteration"), bool)
            and progress.get("current_iteration") == loop.iteration
        )
    return current_matches and visit_matches and runtime_matches and progress_matches


def get_human_input(run_root: Path | str) -> dict[str, Any] | None:
    """Read the latest detached root request from one persisted run."""

    state_file = Path(run_root) / "state.json"
    state = RunState.from_dict(json.loads(state_file.read_text(encoding="utf-8")))
    return None if state.human_input is None else deepcopy(state.human_input)


def record_human_input(
    manager: Any,
    *,
    runtime_step_id: str,
    enclosing_step: Mapping[str, Any],
    loop_iteration: Mapping[str, Any] | None,
    question: str,
) -> dict[str, Any]:
    """Atomically retain the sole outstanding request on the aggregate root."""

    owner = resolve_aggregate_run_owner(manager)
    runtime_step = nonempty_string(runtime_step_id, "human input runtime_step_id")
    enclosing = EnclosingStep.from_dict(enclosing_step)
    loop = None if loop_iteration is None else LoopIteration.from_dict(loop_iteration)
    if not isinstance(question, str):
        raise ValueError("human input question must be a string")
    scope = _scope_to_dict(owner.resume_scope_path)
    identity = (
        scope, runtime_step, enclosing.to_dict(),
        None if loop is None else loop.to_dict(),
    )

    def commit_guard(leaf: RunState) -> bool:
        return human_input_reached_position_matches(
            leaf,
            runtime_step_id=runtime_step,
            enclosing=enclosing,
            loop=loop,
        )

    def mutate(root: RunState, _chain: tuple[RunState, ...]) -> None:
        if root.status not in {"running", "suspended"}:
            raise ValueError("human input root run is not active")
        if root.human_input is not None:
            existing = validate_human_input_record(root.human_input)
            existing_identity = (
                existing["resume_scope"], existing["runtime_step_id"],
                existing["enclosing_step"], existing["loop_iteration"],
            )
            if existing_identity == identity:
                if existing["status"] in {"pending", "answered"} and existing["question"] == question:
                    return
                raise ValueError("human input request identity is no longer pending")
            if existing["status"] != "consumed":
                raise ValueError("human input request already outstanding")
        root.human_input = validate_human_input_record(
            {
                "request_id": str(uuid4()),
                "resume_scope": scope,
                "runtime_step_id": runtime_step,
                "enclosing_step": enclosing.to_dict(),
                "loop_iteration": None if loop is None else loop.to_dict(),
                "question": question,
                "status": "pending",
            }
        )
        root.status = "suspended"

    try:
        owner.root_manager._mutate_scoped_state(
            owner.resume_scope_path,
            commit_guard=commit_guard,
            scoped_mutation=mutate,
        )
    finally:
        refresh = getattr(manager, "_refresh_state_chain_from_root", None)
        if refresh is not None:
            refresh()
    root_state = owner.root_manager.state
    assert root_state is not None and root_state.human_input is not None
    return deepcopy(root_state.human_input)


def _manager_for_run_root(root: Path) -> StateManager:
    """Reconstruct the existing manager without assuming the default runs root."""

    state = RunState.from_dict(
        json.loads((root / "state.json").read_text(encoding="utf-8"))
    )
    declared_root = Path(state.run_root).resolve() if state.run_root else root
    if declared_root != root:
        raise ValueError("human input run root is invalid")
    manager = StateManager(Path.cwd(), run_id=state.run_id, state_dir=root.parent)
    if manager.run_root != root or state.run_id != root.name:
        raise ValueError("human input run root is invalid")
    return manager


def submit_human_input(
    run_root: Path | str,
    request_id: str,
    reply: Mapping[str, Any],
) -> dict[str, Any]:
    """Durably answer the current request under the run's writer lock."""

    root = Path(run_root).resolve()
    request_id = _request_id(request_id)
    parsed_reply = validate_human_reply(reply)
    with run_writer_lock(root):
        manager = _manager_for_run_root(root)
        state = manager.load()
        if state.human_input is None:
            raise ValueError("no human input request is recorded")
        record = validate_human_input_record(state.human_input)
        if record["request_id"] != request_id:
            raise ValueError("human input request is stale")
        if record["status"] in {"answered", "consumed"}:
            if record["reply"] == parsed_reply:
                return deepcopy(record)
            raise ValueError("human input reply conflicts")
        record["status"] = "answered"
        record["reply"] = parsed_reply
        state.human_input = record
        try:
            manager._write_state()
        except BaseException:
            if manager.state_file.exists():
                manager.load()
            raise
        return deepcopy(record)


def consume_human_input(
    manager: Any,
    request_id: str,
    *,
    result: StepResult,
    step_name: str,
    loop_name: str | None = None,
    index: int | None = None,
    loop_projection: IterationStepKeyProjection | None = None,
    nested_node_id: str | None = None,
    artifact_versions: dict[str, list[dict[str, Any]]] | None = None,
    artifact_consumes: dict[str, dict[str, int]] | None = None,
    private_artifact_versions: dict[str, list[dict[str, Any]]] | None = None,
    private_artifact_consumes: dict[str, dict[str, int]] | None = None,
) -> RunState:
    """Atomically publish the answered ordinary result and consume its request."""

    request_id = _request_id(request_id)
    if not isinstance(result, StepResult) or result.status != "completed":
        raise ValueError("human input result must be a successful StepResult")
    if not isinstance(step_name, str) or not step_name:
        raise ValueError("human input result step_name is invalid")
    owner = resolve_aggregate_run_owner(manager)
    scope = _scope_to_dict(owner.resume_scope_path)
    root_state = owner.root_manager.state
    if root_state is None or root_state.human_input is None:
        raise ValueError("no human input request is recorded")
    if root_state.status not in {"running", "suspended"}:
        raise ValueError("human input aggregate root is not active")
    initial = validate_human_input_record(root_state.human_input)
    if initial["request_id"] != request_id:
        raise ValueError("human input request is stale")
    if initial["status"] == "consumed":
        raise ValueError("human input request is already consumed")
    if initial["status"] != "answered":
        raise ValueError("human input request must be answered before consumption")
    if initial["resume_scope"] != scope:
        raise ValueError("human input request scope is stale")
    initial_enclosing = EnclosingStep.from_dict(initial["enclosing_step"])
    initial_loop_value = initial["loop_iteration"]
    initial_loop = (
        None
        if initial_loop_value is None
        else LoopIteration.from_dict(initial_loop_value)
    )

    def commit_guard(leaf: RunState) -> bool:
        return human_input_reached_position_matches(
            leaf,
            runtime_step_id=initial["runtime_step_id"],
            enclosing=initial_enclosing,
            loop=initial_loop,
        )

    def mutate(root: RunState, chain: tuple[RunState, ...]) -> None:
        if root.human_input is None:
            raise ValueError("no human input request is recorded")
        record = validate_human_input_record(root.human_input)
        if record["request_id"] != request_id:
            raise ValueError("human input request is stale")
        if record["status"] == "consumed":
            raise ValueError("human input request is already consumed")
        if record["status"] != "answered":
            raise ValueError("human input request must be answered before consumption")
        if record["resume_scope"] != scope:
            raise ValueError("human input request scope is stale")
        if (
            result.name != step_name
            or result.step_id != record["runtime_step_id"]
            or result.output != record["reply"]
        ):
            raise ValueError("human input result does not match the answered reply")

        enclosing = EnclosingStep.from_dict(record["enclosing_step"])
        loop_value = record["loop_iteration"]
        loop = None if loop_value is None else LoopIteration.from_dict(loop_value)
        leaf = chain[-1]
        if not human_input_reached_position_matches(
            leaf,
            runtime_step_id=record["runtime_step_id"],
            enclosing=enclosing,
            loop=loop,
        ):
            raise ValueError("human input request is no longer at the reached operation")
        if loop is None:
            if (
                loop_name is not None or index is not None
                or loop_projection is not None or nested_node_id is not None
                or step_name != enclosing.step_name
            ):
                raise ValueError("human input direct result placement is invalid")
            result_key = step_name
            clear_current_step = True
        else:
            if (
                loop_name != enclosing.step_name
                or isinstance(index, bool)
                or not isinstance(index, int)
                or index != loop.iteration
                or not isinstance(loop_projection, IterationStepKeyProjection)
                or loop_projection.node_id != loop.loop_step_id
                or loop_projection.frame_key != loop_name
                or not isinstance(nested_node_id, str)
                or nested_node_id not in loop_projection.nested_step_id_suffixes
                or loop_projection.nested_presentation_keys.get(nested_node_id) != step_name
                or loop_projection.runtime_step_id(index, nested_node_id) != record["runtime_step_id"]
            ):
                raise ValueError("human input loop result placement is invalid")
            result_key = loop_projection.step_key(index, nested_node_id)
            clear_current_step = False
        _apply_result_with_dataflow(
            leaf,
            result_key=result_key,
            result=result,
            clear_current_step=clear_current_step,
            artifact_versions=artifact_versions,
            artifact_consumes=artifact_consumes,
            private_artifact_versions=private_artifact_versions,
            private_artifact_consumes=private_artifact_consumes,
        )
        root.human_input = {**record, "status": "consumed"}
        root.status = "running"

    try:
        return owner.root_manager._mutate_scoped_state(
            owner.resume_scope_path,
            commit_guard=commit_guard,
            scoped_mutation=mutate,
        )
    finally:
        refresh = getattr(manager, "_refresh_state_chain_from_root", None)
        if refresh is not None:
            refresh()


__all__ = [
    "HumanInputSuspended", "consume_human_input", "get_human_input", "human_input_reached_position_matches", "record_human_input", "submit_human_input",
    "validate_human_input_record",
]
