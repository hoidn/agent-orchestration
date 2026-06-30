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


def recovery_pointer_to_json(decision: RecoveryDependencyDecision) -> dict[str, str]:
    edge = decision.edge
    blocked = edge.blocked_work
    blocker = edge.blocker_work
    retry = edge.retry_target
    if decision.route == "RETRY_TARGET":
        status = "READY_TO_RETRY"
    elif decision.route == "INVALID_EDGE":
        status = "INVALID"
    else:
        status = "WAITING"
    return {
        "blocked_work_id": blocked.id if blocked is not None else "",
        "blocked_work_source": blocked.source if blocked is not None else "",
        "waiting_on_work_id": blocker.id if blocker is not None else "",
        "waiting_on_work_source": blocker.source if blocker is not None else "",
        "retry_target_id": retry.id if retry is not None else "",
        "retry_target_source": retry.source if retry is not None else "",
        "recovery_pointer_status": status,
    }


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


def _ref_key(ref: WorkRef | None) -> tuple[str, str] | None:
    if ref is None:
        return None
    return ref.source, ref.id


def _ref_payload(key: tuple[str, str]) -> dict[str, str]:
    return {"source": key[0], "id": key[1]}


def _known_ref(row: Mapping[str, Any]) -> tuple[tuple[str, str], dict[str, Any]] | None:
    source = str(row.get("source") or "").strip()
    item_id = str(row.get("id") or row.get("item_id") or row.get("design_gap_id") or "").strip()
    if source not in VALID_SOURCES or not item_id:
        return None
    status = str(row.get("status") or "available").strip() or "available"
    return (source, item_id), {"source": source, "id": item_id, "status": status}


def _all_dependency_edges(run_state: Mapping[str, Any]) -> list[RecoveryDependencyEdge]:
    edges: list[RecoveryDependencyEdge] = []
    for source in sorted(VALID_SOURCES):
        for item_id, entry in sorted(_blocked_entries(run_state, source).items()):
            if not isinstance(entry, Mapping):
                continue
            edge = edge_from_blocked_entry(WorkRef(source=source, id=str(item_id)), entry)
            if edge is not None:
                edges.append(edge)
    return edges


def _cycle_nodes(graph: Mapping[tuple[str, str], tuple[str, str]]) -> set[tuple[str, str]]:
    cycles: set[tuple[str, str]] = set()
    visiting: set[tuple[str, str]] = set()
    visited: set[tuple[str, str]] = set()

    def visit(node: tuple[str, str], stack: list[tuple[str, str]]) -> None:
        if node in visiting:
            try:
                index = stack.index(node)
            except ValueError:
                index = 0
            cycles.update(stack[index:])
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        next_node = graph.get(node)
        if next_node is not None:
            visit(next_node, stack)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return cycles


def _completed_keys(run_state: Mapping[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for source in VALID_SOURCES:
        keys.update((source, item_id) for item_id in _completed_ids(run_state, source))
    return keys


def build_recovery_eligibility(
    known_work: list[Mapping[str, Any]],
    run_state: Mapping[str, Any],
    *,
    target_gap_discovery_allowed: bool = True,
) -> dict[str, Any]:
    """Project recovery dependency state into selectable and hidden work refs."""

    known: dict[tuple[str, str], dict[str, Any]] = {}
    for row in known_work:
        parsed = _known_ref(row)
        if parsed is not None:
            key, payload = parsed
            known[key] = payload

    completed = _completed_keys(run_state)
    edges = _all_dependency_edges(run_state)
    graph: dict[tuple[str, str], tuple[str, str]] = {}
    for edge in edges:
        blocked_key = _ref_key(edge.blocked_work)
        blocker_key = _ref_key(edge.blocker_work)
        if (
            blocked_key is not None
            and blocker_key is not None
            and edge.status not in {"invalid_cycle", "missing_evidence"}
            and not _ready_when_satisfied(edge, run_state)
        ):
            graph[blocked_key] = blocker_key

    cycle_keys = _cycle_nodes(graph)
    hidden: dict[tuple[str, str], dict[str, Any]] = {}
    raw_errors: list[dict[str, Any]] = []
    priority_candidates: set[tuple[str, str]] = set()

    def hide(key: tuple[str, str], reason: str, waiting_on: tuple[str, str] | None = None) -> None:
        payload: dict[str, Any] = {**_ref_payload(key), "reason": reason}
        if waiting_on is not None:
            payload["waiting_on"] = _ref_payload(waiting_on)
        hidden[key] = payload

    for key in sorted(cycle_keys):
        hide(key, "dependency_cycle")
    if cycle_keys:
        raw_errors.append(
            {
                "code": "dependency_cycle",
                "work": [_ref_payload(key) for key in sorted(cycle_keys)],
                "reason": "dependency_cycle",
            }
        )

    for edge in edges:
        blocked_key = _ref_key(edge.blocked_work)
        blocker_key = _ref_key(edge.blocker_work)
        if blocked_key is None:
            raw_errors.append({"code": edge.reason or "missing_work_reference", "reason": edge.reason})
            continue
        if blocked_key in cycle_keys:
            continue
        decision = evaluate_edge(edge, run_state)
        if decision.route == "INVALID_EDGE":
            hide(blocked_key, decision.reason or "invalid_dependency")
            raw_errors.append(
                {
                    "code": decision.reason or "invalid_dependency",
                    "work": _ref_payload(blocked_key),
                    "reason": decision.reason or "invalid_dependency",
                }
            )
            continue
        if decision.route == "RETRY_TARGET":
            continue
        if blocker_key is None:
            hide(blocked_key, "missing_dependency_target")
            raw_errors.append(
                {
                    "code": "missing_dependency_target",
                    "work": _ref_payload(blocked_key),
                    "reason": "missing_dependency_target",
                }
            )
            continue
        hide(blocked_key, "waiting_on_incomplete_dependency", blocker_key)
        if blocker_key not in known and blocker_key not in completed:
            raw_errors.append(
                {
                    "code": "missing_dependency_target",
                    "work": _ref_payload(blocked_key),
                    "missing": _ref_payload(blocker_key),
                    "reason": "missing_dependency_target",
                }
            )
        else:
            priority_candidates.add(blocker_key)

    unavailable_statuses = {"retired", "completed", "invalid"}

    def runnable(key: tuple[str, str]) -> bool:
        row = known.get(key)
        if row is None:
            return False
        if key in completed or key in hidden:
            return False
        return str(row.get("status") or "").strip().lower() not in unavailable_statuses

    eligible = [known[key] for key in sorted(known) if runnable(key)]
    priority = [known[key] for key in sorted(priority_candidates) if runnable(key)]
    blocks_selection = bool(raw_errors and not eligible and not target_gap_discovery_allowed)
    blocking_errors = raw_errors if blocks_selection else []
    diagnostic_errors = [] if blocks_selection else raw_errors

    return {
        "eligible_work": eligible,
        "hidden_work": [hidden[key] for key in sorted(hidden)],
        "priority_recovery_work": priority,
        "blocking_mechanics_errors": blocking_errors,
        "diagnostic_mechanics_errors": diagnostic_errors,
        "hidden_summary": {
            "blocked_by_dependencies": sum(
                1 for item in hidden.values() if item.get("reason") == "waiting_on_incomplete_dependency"
            ),
            "invalid_dependencies": len(raw_errors),
        },
    }
