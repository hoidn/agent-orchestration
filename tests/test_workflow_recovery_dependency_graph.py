from workflows.library.scripts.workflow_recovery_dependencies import (
    WorkRef,
    build_recovery_eligibility,
    edge_from_blocked_entry,
    edge_to_json,
    evaluate_edge,
    normalize_edge,
    recovery_pointer_to_json,
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


def _edge_json(blocked: str, blocker: str, *, source: str = "DESIGN_GAP") -> dict:
    return {
        "blocked_work": {"source": source, "id": blocked},
        "blocker_work": {"source": source, "id": blocker},
        "relation": "requires_completion",
        "reason_code": f"missing_{blocker}",
        "ready_when": {"kind": "completed", "source": source, "id": blocker},
        "retry_target": {"source": source, "id": blocked},
    }


def _state(
    *,
    blocked_design_gaps: dict[str, dict] | None = None,
    completed_design_gaps: list[str] | None = None,
) -> dict:
    return {
        "completed_design_gaps": completed_design_gaps or [],
        "completed_items": [],
        "blocked_design_gaps": blocked_design_gaps or {},
        "blocked_items": {},
    }


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


def test_recovery_pointer_for_waiting_prerequisite():
    decision = evaluate_edge(
        _edge(),
        {"completed_design_gaps": [], "completed_items": [], "blocked_design_gaps": {}, "blocked_items": {}},
    )

    assert recovery_pointer_to_json(decision) == {
        "blocked_work_id": "parser",
        "blocked_work_source": "DESIGN_GAP",
        "waiting_on_work_id": "context",
        "waiting_on_work_source": "DESIGN_GAP",
        "retry_target_id": "parser",
        "retry_target_source": "DESIGN_GAP",
        "recovery_pointer_status": "WAITING",
    }


def test_recovery_pointer_for_ready_to_retry_prerequisite():
    decision = evaluate_edge(
        _edge(),
        {
            "completed_design_gaps": ["context"],
            "completed_items": [],
            "blocked_design_gaps": {},
            "blocked_items": {},
        },
    )

    assert recovery_pointer_to_json(decision) == {
        "blocked_work_id": "parser",
        "blocked_work_source": "DESIGN_GAP",
        "waiting_on_work_id": "context",
        "waiting_on_work_source": "DESIGN_GAP",
        "retry_target_id": "parser",
        "retry_target_source": "DESIGN_GAP",
        "recovery_pointer_status": "READY_TO_RETRY",
    }


def test_recovery_pointer_for_invalid_prerequisite():
    decision = evaluate_edge(
        _edge(blocker_work={"source": "DESIGN_GAP", "id": "parser"}),
        {"completed_design_gaps": [], "completed_items": [], "blocked_design_gaps": {}, "blocked_items": {}},
    )

    assert recovery_pointer_to_json(decision) == {
        "blocked_work_id": "parser",
        "blocked_work_source": "DESIGN_GAP",
        "waiting_on_work_id": "parser",
        "waiting_on_work_source": "DESIGN_GAP",
        "retry_target_id": "parser",
        "retry_target_source": "DESIGN_GAP",
        "recovery_pointer_status": "INVALID",
    }


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


def test_eligibility_hides_dependent_waiting_on_incomplete_prerequisite():
    eligibility = build_recovery_eligibility(
        [
            {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "b", "status": "available"},
        ],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "b"),
                }
            }
        ),
    )

    assert [item["id"] for item in eligibility["eligible_work"]] == ["b"]
    assert [item["id"] for item in eligibility["hidden_work"]] == ["a"]
    assert eligibility["hidden_work"][0]["waiting_on"] == {"source": "DESIGN_GAP", "id": "b"}
    assert [item["id"] for item in eligibility["priority_recovery_work"]] == ["b"]


def test_eligibility_completed_prerequisite_reenables_retry_target():
    eligibility = build_recovery_eligibility(
        [
            {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "b", "status": "completed"},
        ],
        _state(
            completed_design_gaps=["b"],
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "b"),
                }
            },
        ),
    )

    assert [item["id"] for item in eligibility["eligible_work"]] == ["a"]
    assert eligibility["hidden_work"] == []
    assert eligibility["priority_recovery_work"] == []


def test_eligibility_missing_prerequisite_is_diagnostic_when_unrelated_work_exists():
    eligibility = build_recovery_eligibility(
        [
            {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "x", "status": "available"},
        ],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "missing-c"),
                }
            }
        ),
    )

    assert [item["id"] for item in eligibility["eligible_work"]] == ["x"]
    assert [item["id"] for item in eligibility["hidden_work"]] == ["a"]
    assert eligibility["priority_recovery_work"] == []
    assert eligibility["blocking_mechanics_errors"] == []
    assert eligibility["diagnostic_mechanics_errors"][0]["code"] == "missing_dependency_target"
    assert eligibility["diagnostic_mechanics_errors"][0]["missing"] == {
        "source": "DESIGN_GAP",
        "id": "missing-c",
    }


def test_eligibility_missing_prerequisite_stays_diagnostic_when_discovery_allowed():
    eligibility = build_recovery_eligibility(
        [{"source": "DESIGN_GAP", "id": "a", "status": "blocked"}],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "missing-c"),
                }
            }
        ),
    )

    assert eligibility["eligible_work"] == []
    assert eligibility["priority_recovery_work"] == []
    assert eligibility["blocking_mechanics_errors"] == []
    assert eligibility["diagnostic_mechanics_errors"][0]["code"] == "missing_dependency_target"


def test_eligibility_missing_prerequisite_blocks_when_discovery_disabled():
    eligibility = build_recovery_eligibility(
        [{"source": "DESIGN_GAP", "id": "a", "status": "blocked"}],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "missing-c"),
                }
            }
        ),
        target_gap_discovery_allowed=False,
    )

    assert eligibility["eligible_work"] == []
    assert eligibility["priority_recovery_work"] == []
    assert eligibility["blocking_mechanics_errors"][0]["code"] == "missing_dependency_target"
    assert eligibility["diagnostic_mechanics_errors"] == []


def test_eligibility_fixed_point_hides_prerequisite_with_missing_dependency():
    eligibility = build_recovery_eligibility(
        [
            {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "b", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "x", "status": "available"},
        ],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "b"),
                },
                "b": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("b", "missing-c"),
                },
            }
        ),
    )

    assert [item["id"] for item in eligibility["eligible_work"]] == ["x"]
    assert {item["id"] for item in eligibility["hidden_work"]} == {"a", "b"}
    assert eligibility["priority_recovery_work"] == []
    assert eligibility["diagnostic_mechanics_errors"][0]["code"] == "missing_dependency_target"


def test_eligibility_indirect_cycle_hides_all_members_without_priority_work():
    eligibility = build_recovery_eligibility(
        [
            {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "b", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "c", "status": "blocked"},
        ],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "b"),
                },
                "b": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("b", "c"),
                },
                "c": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("c", "a"),
                },
            }
        ),
    )

    assert eligibility["eligible_work"] == []
    assert {item["id"] for item in eligibility["hidden_work"]} == {"a", "b", "c"}
    assert eligibility["priority_recovery_work"] == []
    assert eligibility["blocking_mechanics_errors"] == []
    assert eligibility["diagnostic_mechanics_errors"][0]["code"] == "dependency_cycle"


def test_eligibility_excludes_blocked_prerequisite_from_priority_until_runnable():
    eligibility = build_recovery_eligibility(
        [
            {"source": "DESIGN_GAP", "id": "a", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "b", "status": "blocked"},
            {"source": "DESIGN_GAP", "id": "c", "status": "available"},
        ],
        _state(
            blocked_design_gaps={
                "a": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("a", "b"),
                },
                "b": {
                    "reason": "implementation_blocked",
                    "recovery_dependency_edge": _edge_json("b", "c"),
                },
            }
        ),
    )

    assert [item["id"] for item in eligibility["eligible_work"]] == ["c"]
    assert [item["id"] for item in eligibility["priority_recovery_work"]] == ["c"]
    assert {item["id"] for item in eligibility["hidden_work"]} == {"a", "b"}


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
