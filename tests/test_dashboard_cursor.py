"""Tests for dashboard execution cursor projection."""

from __future__ import annotations

from orchestrator.dashboard.cursor import ExecutionCursorProjector


def test_cursor_projects_top_level_current_step_first():
    cursor = ExecutionCursorProjector().project(
        {
            "current_step": {
                "name": "Draft",
                "step_id": "root.draft",
                "status": "running",
            }
        }
    )

    assert cursor.nodes[0].kind == "current_step"
    assert cursor.nodes[0].name == "Draft"
    assert cursor.summary == "Draft"


def test_cursor_traverses_running_call_frames_recursively_and_breaks_cycles():
    state = {
        "current_step": {"name": "OuterCall", "step_id": "root.outer", "status": "running"},
        "call_frames": {
            "frame1": {
                "status": "running",
                "caller_step_id": "root.outer",
                "workflow_file": "callee.yaml",
                "bound_inputs": {"x": "1"},
                "current_step": {
                    "name": "InnerCall",
                    "step_id": "callee.inner",
                    "status": "running",
                },
            },
            "frame2": {
                "status": "running",
                "caller_step_id": "callee.inner",
                "workflow_file": "nested.yaml",
                "current_step": {
                    "name": "Again",
                    "step_id": "root.outer",
                    "status": "running",
                },
            },
        },
    }

    cursor = ExecutionCursorProjector(max_depth=5).project(state)

    assert [node.name for node in cursor.nodes if node.kind == "current_step"] == [
        "OuterCall",
        "InnerCall",
        "Again",
    ]
    assert any(node.kind == "call_frame" and node.name == "frame1" for node in cursor.nodes)
    assert any("cycle detected" in warning for warning in cursor.warnings)


def test_cursor_projects_loop_and_finalization_state():
    cursor = ExecutionCursorProjector().project(
        {
            "current_step": {"name": "ReviewLoop", "step_id": "root.review_loop"},
            "repeat_until": {
                "ReviewLoop": {
                    "current_iteration": 2,
                    "completed_iterations": [0, 1],
                    "last_condition_result": False,
                }
            },
            "for_each": {
                "ProcessItems": {
                    "items": ["a", "b", "c"],
                    "current_index": 1,
                    "completed_indices": [0],
                }
            },
            "finalization": {
                "status": "running",
                "body_status": "failed",
                "workflow_outputs_status": "suppressed",
            },
        }
    )

    by_kind = {node.kind: node for node in cursor.nodes}
    assert by_kind["repeat_until"].details["current_iteration"] == 2
    assert by_kind["for_each"].details["item_count"] == 3
    assert by_kind["finalization"].details["workflow_outputs_status"] == "suppressed"
