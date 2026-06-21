#!/usr/bin/env python3
"""Pure helpers for workflow recovery dependency routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


VALID_SOURCES = {"DESIGN_GAP", "BACKLOG_ITEM"}
VALID_RELATIONS = {"requires_completion", "requires_retry", "blocked_until_ready"}
VALID_STATUSES = {"waiting", "ready_to_retry", "blocked", "invalid_cycle", "missing_evidence", "completed"}
VALID_ROUTES = {"SELECT_BLOCKER", "RETRY_TARGET", "BLOCKED_RECOVERABLE", "BLOCKED_TERMINAL", "INVALID_EDGE"}
SCHEMA = "workflow_recovery_dependency_edge/v1"


@dataclass(frozen=True)
class WorkRef:
    source: str
    id: str


@dataclass(frozen=True)
class RecoveryDependencyEdge:
    blocked_work: WorkRef | None
    blocker_work: WorkRef | None
    relation: str
    reason_code: str
    ready_when: dict[str, str]
    retry_target: WorkRef | None
    downstream_work: tuple[WorkRef, ...] = ()
    status: str = "waiting"
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoveryDependencyDecision:
    route: str
    target: WorkRef | None
    edge: RecoveryDependencyEdge
    reason: str

    def __post_init__(self) -> None:
        if self.route not in VALID_ROUTES:
            raise ValueError(f"Unexpected recovery dependency route: {self.route}")


def _work_ref(raw: Any) -> WorkRef | None:
    if not isinstance(raw, Mapping):
        return None
    source = str(raw.get("source") or "").strip()
    item_id = str(raw.get("id") or "").strip()
    if source not in VALID_SOURCES or not item_id:
        return None
    return WorkRef(source=source, id=item_id)


def _ready_when(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, str] = {}
    for key in ("kind", "source", "id"):
        value = str(raw.get(key) or "").strip()
        if value:
            result[key] = value
    return result


def _downstream_work(raw: Any) -> tuple[WorkRef, ...]:
    if not isinstance(raw, list):
        return ()
    refs = []
    for item in raw:
        ref = _work_ref(item)
        if ref is not None:
            refs.append(ref)
    return tuple(refs)


def _invalid(raw: Mapping[str, Any], reason: str) -> RecoveryDependencyEdge:
    return RecoveryDependencyEdge(
        blocked_work=_work_ref(raw.get("blocked_work")),
        blocker_work=_work_ref(raw.get("blocker_work")),
        relation=str(raw.get("relation") or "").strip(),
        reason_code=str(raw.get("reason_code") or "").strip(),
        ready_when=_ready_when(raw.get("ready_when")),
        retry_target=_work_ref(raw.get("retry_target")),
        downstream_work=_downstream_work(raw.get("downstream_work")),
        status="invalid_cycle" if reason.endswith("_dependency") else "missing_evidence",
        reason=reason,
        evidence=dict(raw.get("evidence") or {}) if isinstance(raw.get("evidence"), Mapping) else {},
    )


def normalize_edge(raw: Mapping[str, Any]) -> RecoveryDependencyEdge:
    """Normalize an untrusted recovery dependency edge.

    The function never raises for malformed edge content; it returns an edge with
    `missing_evidence` or `invalid_cycle` so routing can fail closed.
    """

    blocked = _work_ref(raw.get("blocked_work"))
    if blocked is None:
        return _invalid(raw, "missing_blocked_work")
    blocker = _work_ref(raw.get("blocker_work"))
    if blocker is None:
        return _invalid(raw, "missing_blocker_work")
    relation = str(raw.get("relation") or "").strip()
    if relation not in VALID_RELATIONS:
        return _invalid(raw, "unsupported_relation")
    retry_target = _work_ref(raw.get("retry_target"))
    if retry_target is None:
        return _invalid(raw, "missing_retry_target")
    reason_code = str(raw.get("reason_code") or "").strip()
    if not reason_code:
        return _invalid(raw, "missing_reason_code")
    ready_when = _ready_when(raw.get("ready_when"))
    if not ready_when:
        return _invalid(raw, "missing_ready_when")
    status = str(raw.get("status") or "waiting").strip()
    if status not in VALID_STATUSES:
        return _invalid(raw, "unsupported_status")
    if relation == "requires_completion" and blocked == blocker:
        return RecoveryDependencyEdge(
            blocked_work=blocked,
            blocker_work=blocker,
            relation=relation,
            reason_code=reason_code,
            ready_when=ready_when,
            retry_target=retry_target,
            downstream_work=_downstream_work(raw.get("downstream_work")),
            status="invalid_cycle",
            reason="self_completion_dependency",
            evidence=dict(raw.get("evidence") or {}) if isinstance(raw.get("evidence"), Mapping) else {},
        )
    if relation == "requires_retry" and blocked == blocker and ready_when.get("kind") not in {"completed", "retry"}:
        return RecoveryDependencyEdge(
            blocked_work=blocked,
            blocker_work=blocker,
            relation=relation,
            reason_code=reason_code,
            ready_when=ready_when,
            retry_target=retry_target,
            downstream_work=_downstream_work(raw.get("downstream_work")),
            status="missing_evidence",
            reason="self_retry_missing_evidence",
            evidence=dict(raw.get("evidence") or {}) if isinstance(raw.get("evidence"), Mapping) else {},
        )
    return RecoveryDependencyEdge(
        blocked_work=blocked,
        blocker_work=blocker,
        relation=relation,
        reason_code=reason_code,
        ready_when=ready_when,
        retry_target=retry_target,
        downstream_work=_downstream_work(raw.get("downstream_work")),
        status=status,
        reason=str(raw.get("reason") or "").strip(),
        evidence=dict(raw.get("evidence") or {}) if isinstance(raw.get("evidence"), Mapping) else {},
    )


def edge_to_json(edge: RecoveryDependencyEdge) -> dict[str, Any]:
    def ref_json(ref: WorkRef | None) -> dict[str, str]:
        return {"source": ref.source, "id": ref.id} if ref is not None else {}

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "blocked_work": ref_json(edge.blocked_work),
        "blocker_work": ref_json(edge.blocker_work),
        "relation": edge.relation,
        "reason_code": edge.reason_code,
        "ready_when": dict(edge.ready_when),
        "retry_target": ref_json(edge.retry_target),
        "downstream_work": [ref_json(ref) for ref in edge.downstream_work],
        "status": edge.status,
        "reason": edge.reason,
        "evidence": dict(edge.evidence),
    }
    return payload


def _completed_ids(run_state: Mapping[str, Any], source: str) -> set[str]:
    if source == "DESIGN_GAP":
        return {str(item) for item in run_state.get("completed_design_gaps") or []}
    if source == "BACKLOG_ITEM":
        return {str(item) for item in run_state.get("completed_items") or []}
    return set()


def _blocked_entries(run_state: Mapping[str, Any], source: str) -> Mapping[str, Any]:
    if source == "DESIGN_GAP":
        return run_state.get("blocked_design_gaps") or {}
    if source == "BACKLOG_ITEM":
        return run_state.get("blocked_items") or {}
    return {}


def _is_completed(run_state: Mapping[str, Any], ref: WorkRef | None) -> bool:
    return ref is not None and ref.id in _completed_ids(run_state, ref.source)


def _ready_when_satisfied(edge: RecoveryDependencyEdge, run_state: Mapping[str, Any]) -> bool:
    if edge.ready_when.get("kind") == "completed":
        ref = _work_ref({"source": edge.ready_when.get("source"), "id": edge.ready_when.get("id")})
        return _is_completed(run_state, ref)
    if edge.ready_when.get("kind") == "retry":
        return edge.status == "ready_to_retry"
    return False


def _is_recoverable_blocked(entry: Any) -> bool:
    if not isinstance(entry, Mapping):
        return False
    if str(entry.get("reason") or "").strip() != "implementation_blocked":
        return False
    route = str(entry.get("recovery_route") or "").strip()
    return bool(route and route != "TERMINAL_BLOCKED" and str(entry.get("recovery_event_id") or "").strip())


def _has_reverse_dependency(edge: RecoveryDependencyEdge, run_state: Mapping[str, Any]) -> bool:
    if edge.blocked_work is None or edge.blocker_work is None:
        return False
    blocker_entry = _blocked_entries(run_state, edge.blocker_work.source).get(edge.blocker_work.id)
    if not isinstance(blocker_entry, Mapping):
        return False
    blocker_edge = edge_from_blocked_entry(edge.blocker_work, blocker_entry)
    return blocker_edge is not None and blocker_edge.blocker_work == edge.blocked_work


def evaluate_edge(edge: RecoveryDependencyEdge, run_state: Mapping[str, Any]) -> RecoveryDependencyDecision:
    if edge.status in {"invalid_cycle", "missing_evidence"}:
        return RecoveryDependencyDecision("INVALID_EDGE", None, edge, edge.reason or edge.status)
    if edge.blocked_work is None or edge.blocker_work is None or edge.retry_target is None:
        return RecoveryDependencyDecision("INVALID_EDGE", None, edge, "missing_work_reference")
    if _has_reverse_dependency(edge, run_state):
        return RecoveryDependencyDecision("INVALID_EDGE", None, edge, "dependency_cycle")
    if _ready_when_satisfied(edge, run_state):
        return RecoveryDependencyDecision("RETRY_TARGET", edge.retry_target, edge, "ready_when_satisfied")
    blocker_entry = _blocked_entries(run_state, edge.blocker_work.source).get(edge.blocker_work.id)
    if _is_recoverable_blocked(blocker_entry):
        return RecoveryDependencyDecision("BLOCKED_RECOVERABLE", edge.blocker_work, edge, "blocker_recoverable")
    if isinstance(blocker_entry, Mapping) and str(blocker_entry.get("recovery_route") or "").strip() == "TERMINAL_BLOCKED":
        return RecoveryDependencyDecision("BLOCKED_TERMINAL", edge.blocker_work, edge, "blocker_terminal")
    return RecoveryDependencyDecision("SELECT_BLOCKER", edge.blocker_work, edge, "blocker_pending")


def edge_from_blocked_entry(blocked_work: WorkRef, entry: Mapping[str, Any]) -> RecoveryDependencyEdge | None:
    explicit = entry.get("recovery_dependency_edge")
    if isinstance(explicit, Mapping):
        return normalize_edge(explicit)

    prerequisite_id = str(entry.get("waiting_on_prerequisite_gap_id") or "").strip()
    if not prerequisite_id:
        return None
    prerequisite_source = str(entry.get("waiting_on_prerequisite_source") or "DESIGN_GAP").strip()
    downstream_id = str(entry.get("downstream_blocked_gap_id") or "").strip()
    legacy_fields = {
        key: entry[key]
        for key in (
            "waiting_on_prerequisite_gap_id",
            "waiting_on_prerequisite_source",
            "downstream_blocked_gap_id",
            "blocking_failure_code",
            "retry_condition",
            "prerequisite_recovery_status",
            "prerequisite_recovery_reason",
        )
        if key in entry
    }
    raw: dict[str, Any] = {
        "blocked_work": {"source": blocked_work.source, "id": blocked_work.id},
        "blocker_work": {"source": prerequisite_source, "id": prerequisite_id},
        "relation": "requires_completion",
        "reason_code": str(entry.get("blocking_failure_code") or entry.get("recovery_reason") or "prerequisite_required"),
        "ready_when": {"kind": "completed", "source": prerequisite_source, "id": prerequisite_id},
        "retry_target": {"source": blocked_work.source, "id": blocked_work.id},
        "downstream_work": (
            [{"source": "DESIGN_GAP", "id": downstream_id}]
            if downstream_id and downstream_id != blocked_work.id
            else []
        ),
        "status": "waiting",
        "evidence": {"legacy_fields": legacy_fields},
    }
    return normalize_edge(raw)

