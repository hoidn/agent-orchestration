"""Root-owned functional identity for durable provider attempts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ..state import RunState, StateManager
from .identity import STEP_ID_PATTERN
from .resume_projection_integrity import ResumeScopePath


@dataclass(frozen=True)
class AggregateRunOwner:
    """Validated terminal owner and reached leaf for one runtime manager."""

    root_manager: StateManager
    resume_scope_path: ResumeScopePath
    leaf_state: RunState
    aggregate_root: Path


def _closed_mapping(value: Any, keys: set[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{field} must be a closed object with keys {sorted(keys)}")
    return value


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _ordinary_integer(value: Any, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class EnclosingStep:
    step_name: str
    step_id: str
    visit_count: int

    @classmethod
    def from_dict(cls, value: Any) -> "EnclosingStep":
        node = _closed_mapping(
            value,
            {"step_name", "step_id", "visit_count"},
            "enclosing_step",
        )
        return cls(
            step_name=_nonempty_string(node["step_name"], "enclosing_step.step_name"),
            step_id=_nonempty_string(node["step_id"], "enclosing_step.step_id"),
            visit_count=_ordinary_integer(
                node["visit_count"], "enclosing_step.visit_count", minimum=1
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "step_id": self.step_id,
            "visit_count": self.visit_count,
        }


@dataclass(frozen=True)
class LoopIteration:
    kind: str
    loop_step_id: str
    iteration: int

    @classmethod
    def from_dict(cls, value: Any) -> "LoopIteration":
        node = _closed_mapping(
            value,
            {"kind", "loop_step_id", "iteration"},
            "loop_iteration",
        )
        kind = node["kind"]
        if kind not in {"for_each", "repeat_until"}:
            raise ValueError("loop_iteration.kind is invalid")
        return cls(
            kind=kind,
            loop_step_id=_nonempty_string(
                node["loop_step_id"], "loop_iteration.loop_step_id"
            ),
            iteration=_ordinary_integer(
                node["iteration"], "loop_iteration.iteration", minimum=0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "loop_step_id": self.loop_step_id,
            "iteration": self.iteration,
        }


@dataclass(frozen=True)
class AdjudicationSubject:
    candidate_id: str

    @classmethod
    def from_dict(cls, value: Any) -> "AdjudicationSubject":
        node = _closed_mapping(value, {"candidate_id"}, "adjudication_subject")
        candidate_id = _nonempty_string(
            node["candidate_id"], "adjudication_subject.candidate_id"
        )
        if STEP_ID_PATTERN.fullmatch(candidate_id) is None:
            raise ValueError("adjudication_subject.candidate_id is invalid")
        return cls(candidate_id=candidate_id)

    def to_dict(self) -> dict[str, str]:
        return {"candidate_id": self.candidate_id}


@dataclass(frozen=True)
class ProviderAttemptScope:
    """Closed persisted execution identity for one provider attempt visit."""

    run_id: str
    resume_scope: ResumeScopePath
    runtime_step_id: str
    enclosing_step: EnclosingStep
    loop_iteration: LoopIteration | None
    adjudication_subject: AdjudicationSubject | None

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderAttemptScope":
        node = _closed_mapping(
            value,
            {
                "run_id",
                "resume_scope",
                "runtime_step_id",
                "enclosing_step",
                "loop_iteration",
                "adjudication_subject",
            },
            "provider_attempt_scope",
        )
        resume_node = _closed_mapping(
            node["resume_scope"],
            {"root_workflow_file", "call_frame_ids"},
            "resume_scope",
        )
        call_frame_ids = resume_node["call_frame_ids"]
        if not isinstance(call_frame_ids, list):
            raise ValueError("resume_scope.call_frame_ids must be a list")
        resume_scope = ResumeScopePath(
            _nonempty_string(
                resume_node["root_workflow_file"],
                "resume_scope.root_workflow_file",
            ),
            tuple(call_frame_ids),
        )
        loop_node = node["loop_iteration"]
        adjudication_node = node["adjudication_subject"]
        return cls(
            run_id=_nonempty_string(node["run_id"], "run_id"),
            resume_scope=resume_scope,
            runtime_step_id=_nonempty_string(node["runtime_step_id"], "runtime_step_id"),
            enclosing_step=EnclosingStep.from_dict(node["enclosing_step"]),
            loop_iteration=(
                None if loop_node is None else LoopIteration.from_dict(loop_node)
            ),
            adjudication_subject=(
                None
                if adjudication_node is None
                else AdjudicationSubject.from_dict(adjudication_node)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "resume_scope": {
                "root_workflow_file": self.resume_scope.root_workflow_file,
                "call_frame_ids": list(self.resume_scope.call_frame_ids),
            },
            "runtime_step_id": self.runtime_step_id,
            "enclosing_step": self.enclosing_step.to_dict(),
            "loop_iteration": (
                None if self.loop_iteration is None else self.loop_iteration.to_dict()
            ),
            "adjudication_subject": (
                None
                if self.adjudication_subject is None
                else self.adjudication_subject.to_dict()
            ),
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    @property
    def key(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()


def _ordinary_absolute(path: Any) -> Path:
    return Path(path).absolute()


def bundle_requires_provider_attempt_coordination(bundle: Any) -> bool:
    """Return whether a recursive executable bundle contains an allocator contract."""

    pending = [bundle]
    seen: set[int] = set()
    affected = False
    while pending:
        current = pending.pop()
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        ir = getattr(current, "ir", None)
        nodes = getattr(ir, "nodes", None)
        imports = getattr(current, "imports", None)
        if not isinstance(nodes, Mapping) or not isinstance(imports, Mapping):
            raise TypeError("executable workflow bundle required")
        for node in nodes.values():
            config = getattr(node, "execution_config", None)
            if getattr(config, "compiler_prompt_dependency_contract", None) is not None:
                affected = True
        pending.extend(imports.values())
    return affected


def enable_provider_attempt_coordination_for_bundle(
    manager: StateManager,
    bundle: Any,
) -> bool:
    """Enable root-state coordination before mutating an affected bundle's state."""

    if not isinstance(manager, StateManager):
        raise TypeError("StateManager required")
    affected = bundle_requires_provider_attempt_coordination(bundle)
    if affected:
        manager.enable_durable_state_writes()
    return affected


def resolve_aggregate_run_owner(manager: Any) -> AggregateRunOwner:
    """Resolve and validate the terminal root owner for ``manager``."""

    seen: set[int] = set()
    cursor = manager
    nested_from_leaf: list[Any] = []
    frame_ids_from_leaf: list[str] = []
    while not isinstance(cursor, StateManager):
        identity = id(cursor)
        if identity in seen:
            raise ValueError("parent_manager cycle detected")
        seen.add(identity)
        if not hasattr(cursor, "parent_manager"):
            raise TypeError("aggregate terminal root must be a StateManager")
        frame_id = getattr(cursor, "frame_id", None)
        if not isinstance(frame_id, str) or not frame_id:
            raise ValueError("nested manager call frame identity is invalid")
        nested_state = getattr(cursor, "state", None)
        if not isinstance(nested_state, RunState):
            raise ValueError("nested state must be a RunState")
        nested_from_leaf.append(cursor)
        frame_ids_from_leaf.append(frame_id)
        cursor = cursor.parent_manager
        if id(cursor) in seen:
            raise ValueError("parent_manager cycle detected")

    root = cursor
    if not isinstance(root.state, RunState):
        raise ValueError("aggregate root state is not initialized")
    root_state = root.state
    aggregate_root = _ordinary_absolute(root.run_root)
    if root.run_id != root_state.run_id:
        raise ValueError("root run_id contradicts persisted state")
    if root_state.run_root is None or _ordinary_absolute(root_state.run_root) != aggregate_root:
        raise ValueError("root run_root contradicts persisted state")

    nested_from_root = list(reversed(nested_from_leaf))
    frame_ids = tuple(reversed(frame_ids_from_leaf))
    scope_path = ResumeScopePath(root_state.workflow_file, frame_ids)
    current_state = root_state
    parent_manager: Any = root
    prefix_frame_ids: list[str] = []
    for child in nested_from_root:
        prefix_frame_ids.append(child.frame_id)
        expected_scope_prefix = ResumeScopePath(
            root_state.workflow_file,
            tuple(prefix_frame_ids),
        )
        if getattr(child, "resume_scope_path", None) != expected_scope_prefix:
            raise ValueError("nested manager scope path prefix contradicts parent chain")
        if child.run_id != root.run_id or child.state.run_id != root.run_id:
            raise ValueError("nested run_id contradicts aggregate root")
        if child.state.provider_attempt_allocations:
            raise ValueError("provider attempt allocator is root-owned, not nested")
        if _ordinary_absolute(child.workspace) != _ordinary_absolute(root.workspace):
            raise ValueError("nested workspace root contradicts aggregate root")

        from .call_frame_state import _path_safe_frame_scope_token

        expected_root = (
            _ordinary_absolute(parent_manager.run_root)
            / "call_frames"
            / _path_safe_frame_scope_token(child.frame_id)
        )
        if _ordinary_absolute(child.run_root) != expected_root:
            raise ValueError("nested run_root contradicts deterministic call-frame root")
        if child.state.run_root is None or _ordinary_absolute(child.state.run_root) != expected_root:
            raise ValueError("nested state run_root contradicts deterministic call-frame root")

        frame = current_state.call_frames.get(child.frame_id)
        if not isinstance(frame, dict):
            raise ValueError("scope path call frame is missing")
        if frame.get("call_frame_id") != child.frame_id:
            raise ValueError("call frame snapshot identity contradicts scope path")
        nested_payload = frame.get("state")
        if not isinstance(nested_payload, dict):
            raise ValueError("nested state snapshot is malformed")
        try:
            parsed = RunState.from_dict(nested_payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("nested state snapshot is malformed") from exc
        if parsed.provider_attempt_allocations:
            raise ValueError("provider attempt allocator is root-owned, not nested")
        if parsed.to_dict() != child.state.to_dict():
            raise ValueError("nested state snapshot contradicts live call frame")
        current_state = parsed
        parent_manager = child

    return AggregateRunOwner(
        root_manager=root,
        resume_scope_path=scope_path,
        leaf_state=current_state,
        aggregate_root=aggregate_root,
    )


def validate_provider_attempt_scope(
    scope: ProviderAttemptScope,
    owner: AggregateRunOwner,
) -> None:
    """Validate a closed scope against its authoritative reached leaf state."""

    if not isinstance(scope, ProviderAttemptScope):
        raise TypeError("ProviderAttemptScope required")
    if not isinstance(owner, AggregateRunOwner):
        raise TypeError("AggregateRunOwner required")
    if scope.run_id != owner.root_manager.run_id:
        raise ValueError("provider attempt run_id contradicts aggregate root")
    if scope.resume_scope != owner.resume_scope_path:
        raise ValueError("provider attempt resume scope contradicts aggregate owner")

    leaf = owner.leaf_state
    enclosing = scope.enclosing_step
    visit = leaf.step_visits.get(enclosing.step_name)
    if (
        isinstance(visit, bool)
        or not isinstance(visit, int)
        or visit <= 0
        or visit != enclosing.visit_count
    ):
        raise ValueError("enclosing step visit_count contradicts leaf state")

    current_step = leaf.current_step
    if isinstance(current_step, Mapping):
        expected = {
            "name": enclosing.step_name,
            "step_id": enclosing.step_id,
            "visit_count": enclosing.visit_count,
        }
        if any(current_step.get(key) != value for key, value in expected.items()):
            raise ValueError("current_step contradicts provider attempt scope")

    loop = scope.loop_iteration
    if loop is None:
        if scope.runtime_step_id != enclosing.step_id:
            raise ValueError("direct provider runtime step contradicts enclosing step")
        return
    if loop.loop_step_id != enclosing.step_id:
        raise ValueError("loop step identity contradicts enclosing step")
    runtime_prefix = f"{loop.loop_step_id}#{loop.iteration}."
    if (
        not scope.runtime_step_id.startswith(runtime_prefix)
        or not scope.runtime_step_id[len(runtime_prefix):]
    ):
        raise ValueError(
            "loop runtime_step_id contradicts canonical iteration projection"
        )
    if loop.kind == "for_each":
        progress = leaf.for_each.get(enclosing.step_name)
        iteration = progress.current_index if progress is not None else None
    else:
        progress = leaf.repeat_until.get(enclosing.step_name)
        iteration = progress.get("current_iteration") if isinstance(progress, Mapping) else None
    if isinstance(iteration, bool) or iteration != loop.iteration:
        raise ValueError("loop iteration contradicts leaf state")


def validate_provider_attempt_allocations(value: Any) -> dict[str, Any]:
    """Validate and normalize the complete closed allocator projection."""

    if not isinstance(value, Mapping):
        raise ValueError("provider attempt allocations must be an object")
    normalized: dict[str, Any] = {}
    for key, raw_entry in value.items():
        if not isinstance(key, str):
            raise ValueError("provider attempt allocation key must be a string")
        entry = _closed_mapping(
            raw_entry,
            {"scope", "last_allocated_ordinal", "events"},
            "provider attempt allocation entry",
        )
        try:
            scope = ProviderAttemptScope.from_dict(entry["scope"])
        except (TypeError, ValueError) as exc:
            raise ValueError("provider attempt allocation scope is invalid") from exc
        if key != scope.key:
            raise ValueError("provider attempt allocation key contradicts scope")
        last_ordinal = _ordinary_integer(
            entry["last_allocated_ordinal"],
            "provider attempt allocation last ordinal",
            minimum=1,
        )
        raw_events = entry["events"]
        if not isinstance(raw_events, list):
            raise ValueError("provider attempt allocation events must be a list")
        events: list[dict[str, Any]] = []
        allocated_ordinals: set[int] = set()
        published_ordinals: set[int] = set()
        publication_events: dict[int, dict[str, Any]] = {}
        previous_allocated = 0
        for raw_event in raw_events:
            if not isinstance(raw_event, Mapping):
                raise ValueError("provider attempt allocation event must be an object")
            event_kind = raw_event.get("event")
            if event_kind == "allocated":
                event = _closed_mapping(
                    raw_event,
                    {"ordinal", "event"},
                    "provider attempt allocated event",
                )
                ordinal = _ordinary_integer(
                    event["ordinal"], "provider attempt event ordinal", minimum=1
                )
                if ordinal <= previous_allocated or ordinal in allocated_ordinals:
                    raise ValueError("provider attempt allocation events are duplicate or reordered")
                previous_allocated = ordinal
                allocated_ordinals.add(ordinal)
                events.append({"ordinal": ordinal, "event": "allocated"})
            elif event_kind == "evidence_published":
                event = _closed_mapping(
                    raw_event,
                    {
                        "ordinal",
                        "event",
                        "relative_path",
                        "file_sha256",
                        "record_kind",
                    },
                    "provider attempt publication event",
                )
                ordinal = _ordinary_integer(
                    event["ordinal"], "provider attempt event ordinal", minimum=1
                )
                if ordinal not in allocated_ordinals or ordinal in published_ordinals:
                    raise ValueError("provider attempt allocation publication is conflicting or reordered")
                relative_path = _nonempty_string(
                    event["relative_path"], "provider attempt publication relative_path"
                )
                file_sha256 = _nonempty_string(
                    event["file_sha256"], "provider attempt publication file_sha256"
                )
                if (
                    not file_sha256.startswith("sha256:")
                    or len(file_sha256) != 71
                    or any(
                        character not in "0123456789abcdef"
                        for character in file_sha256[7:]
                    )
                ):
                    raise ValueError("provider attempt publication file_sha256 is invalid")
                record_kind = event["record_kind"]
                if record_kind not in {"prompt_snapshot", "failure"}:
                    raise ValueError("provider attempt publication record_kind is invalid")
                published_ordinals.add(ordinal)
                normalized_publication = {
                    "ordinal": ordinal,
                    "event": "evidence_published",
                    "relative_path": relative_path,
                    "file_sha256": file_sha256,
                    "record_kind": record_kind,
                }
                publication_events[ordinal] = normalized_publication
                events.append(normalized_publication)
            else:
                raise ValueError("provider attempt allocation event kind is invalid")
        if allocated_ordinals != set(range(1, last_ordinal + 1)):
            raise ValueError("provider attempt allocation last ordinal contradicts events")
        canonical_events: list[dict[str, Any]] = []
        for ordinal in range(1, last_ordinal + 1):
            canonical_events.append({"ordinal": ordinal, "event": "allocated"})
            publication = publication_events.get(ordinal)
            if publication is not None:
                canonical_events.append(publication)
        if events != canonical_events:
            raise ValueError("provider attempt allocation events are not canonical")
        normalized[key] = {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": last_ordinal,
            "events": events,
        }
    return normalized
