from workflows.library.scripts.workflow_recovery_dependencies import (
    WorkRef,
    edge_from_blocked_entry,
    edge_to_json,
    evaluate_edge,
    normalize_edge,
)


def _edge(**overrides):
    raw = {
        "blocked_work": {"source": "DESIGN_GAP", "id": "parser"},
        "blocker_work": {"source": "DESIGN_GAP", "id": "context"},
        "relation": "requires_completion",
        "reason_code": "missing_context",
        "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "context"},
        "retry_target": {"source": "DESIGN_GAP", "id": "parser"},
    }
    raw.update(overrides)
    return normalize_edge(raw)


def test_normalize_dependency_edge_requires_distinct_completion_blocker():
    edge = _edge(blocker_work={"source": "DESIGN_GAP", "id": "parser"})

    assert edge.status == "invalid_cycle"
    assert edge.reason == "self_completion_dependency"


def test_normalize_dependency_edge_accepts_valid_completion_blocker():
    edge = _edge()

    assert edge.status == "waiting"
    assert edge.blocked_work == WorkRef(source="DESIGN_GAP", id="parser")
    assert edge.blocker_work == WorkRef(source="DESIGN_GAP", id="context")


def test_normalize_dependency_edge_accepts_self_retry_with_retry_evidence():
    edge = _edge(
        blocker_work={"source": "DESIGN_GAP", "id": "parser"},
        relation="requires_retry",
        ready_when={"kind": "retry", "source": "DESIGN_GAP", "id": "parser"},
    )

    assert edge.status == "waiting"
    assert edge.reason == ""


def test_normalize_dependency_edge_rejects_missing_blocked_work():
    edge = normalize_edge(
        {
            "blocker_work": {"source": "DESIGN_GAP", "id": "context"},
            "relation": "requires_completion",
            "reason_code": "missing_context",
            "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "context"},
            "retry_target": {"source": "DESIGN_GAP", "id": "parser"},
        }
    )

    assert edge.status == "missing_evidence"
    assert edge.reason == "missing_blocked_work"


def test_normalize_dependency_edge_rejects_missing_blocker_work():
    edge = _edge(blocker_work={})

    assert edge.status == "missing_evidence"
    assert edge.reason == "missing_blocker_work"


def test_normalize_dependency_edge_rejects_unsupported_relation():
    edge = _edge(relation="depends_on_vibes")

    assert edge.status == "missing_evidence"
    assert edge.reason == "unsupported_relation"


def test_completed_blocker_routes_retry_target():
    edge = _edge()
    decision = evaluate_edge(
        edge,
        {
            "completed_design_gaps": ["context"],
            "completed_items": [],
            "blocked_design_gaps": {},
            "blocked_items": {},
        },
    )

    assert decision.route == "RETRY_TARGET"
    assert decision.target == WorkRef(source="DESIGN_GAP", id="parser")


def test_incomplete_blocker_routes_to_select_blocker():
    decision = evaluate_edge(
        _edge(),
        {"completed_design_gaps": [], "completed_items": [], "blocked_design_gaps": {}, "blocked_items": {}},
    )

    assert decision.route == "SELECT_BLOCKER"
    assert decision.target == WorkRef(source="DESIGN_GAP", id="context")


def test_recoverable_blocked_blocker_routes_blocked_recoverable():
    decision = evaluate_edge(
        _edge(),
        {
            "completed_design_gaps": [],
            "completed_items": [],
            "blocked_design_gaps": {
                "context": {
                    "reason": "implementation_blocked",
                    "recovery_route": "GAP_DESIGN_REVISION_REQUIRED",
                    "recovery_event_id": "context-blocked",
                }
            },
            "blocked_items": {},
        },
    )

    assert decision.route == "BLOCKED_RECOVERABLE"
    assert decision.target == WorkRef(source="DESIGN_GAP", id="context")


def test_reverse_dependency_cycle_is_invalid():
    decision = evaluate_edge(
        _edge(),
        {
            "completed_design_gaps": [],
            "completed_items": [],
            "blocked_design_gaps": {
                "context": {
                    "waiting_on_prerequisite_gap_id": "parser",
                    "waiting_on_prerequisite_source": "DESIGN_GAP",
                }
            },
            "blocked_items": {},
        },
    )

    assert decision.route == "INVALID_EDGE"
    assert decision.reason == "dependency_cycle"


def test_downstream_work_waits_while_upstream_blocker_is_waiting():
    edge = _edge(downstream_work=[{"source": "DESIGN_GAP", "id": "summary"}])

    decision = evaluate_edge(
        edge,
        {"completed_design_gaps": [], "completed_items": [], "blocked_design_gaps": {}, "blocked_items": {}},
    )

    assert decision.route == "SELECT_BLOCKER"
    assert edge.downstream_work == (WorkRef(source="DESIGN_GAP", id="summary"),)


def test_completed_evidence_for_wrong_source_does_not_satisfy_edge():
    edge = _edge(
        blocker_work={"source": "BACKLOG_ITEM", "id": "context"},
        ready_when={"kind": "completed", "source": "BACKLOG_ITEM", "id": "context"},
    )

    decision = evaluate_edge(
        edge,
        {
            "completed_design_gaps": ["context"],
            "completed_items": [],
            "blocked_design_gaps": {},
            "blocked_items": {},
        },
    )

    assert decision.route == "SELECT_BLOCKER"


def test_explicit_edge_round_trips_to_json_shape():
    edge = _edge(downstream_work=[{"source": "DESIGN_GAP", "id": "summary"}])
    payload = edge_to_json(edge)

    assert payload["schema"] == "workflow_recovery_dependency_edge/v1"
    assert payload["blocked_work"] == {"source": "DESIGN_GAP", "id": "parser"}
    assert payload["downstream_work"] == [{"source": "DESIGN_GAP", "id": "summary"}]


def test_edge_from_blocked_entry_prefers_explicit_edge():
    edge = edge_from_blocked_entry(
        WorkRef(source="DESIGN_GAP", id="parser"),
        {
            "recovery_dependency_edge": {
                "blocked_work": {"source": "DESIGN_GAP", "id": "parser"},
                "blocker_work": {"source": "DESIGN_GAP", "id": "context"},
                "relation": "requires_completion",
                "reason_code": "missing_context",
                "ready_when": {"kind": "completed", "source": "DESIGN_GAP", "id": "context"},
                "retry_target": {"source": "DESIGN_GAP", "id": "parser"},
            }
        },
    )

    assert edge is not None
    assert edge.blocker_work == WorkRef(source="DESIGN_GAP", id="context")


def test_edge_from_blocked_entry_imports_legacy_fields():
    edge = edge_from_blocked_entry(
        WorkRef(source="DESIGN_GAP", id="parser"),
        {
            "waiting_on_prerequisite_gap_id": "context",
            "waiting_on_prerequisite_source": "DESIGN_GAP",
            "downstream_blocked_gap_id": "summary",
            "blocking_failure_code": "missing_context",
            "retry_condition": "context completes",
        },
    )

    assert edge is not None
    assert edge.status == "waiting"
    assert edge.blocker_work == WorkRef(source="DESIGN_GAP", id="context")
    assert edge.downstream_work == (WorkRef(source="DESIGN_GAP", id="summary"),)
    assert "legacy_fields" in edge.evidence


def test_edge_from_blocked_entry_preserves_legacy_self_completion_as_invalid():
    edge = edge_from_blocked_entry(
        WorkRef(source="DESIGN_GAP", id="parser"),
        {
            "waiting_on_prerequisite_gap_id": "parser",
            "waiting_on_prerequisite_source": "DESIGN_GAP",
            "blocking_failure_code": "missing_context",
        },
    )

    assert edge is not None
    assert edge.status == "invalid_cycle"
    assert edge.reason == "self_completion_dependency"
