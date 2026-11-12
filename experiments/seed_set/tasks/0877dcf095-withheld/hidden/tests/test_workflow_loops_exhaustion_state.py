"""Unit coverage for repeat_until exhaustion-state recognition (loop/recur `:on-exhausted`).

The generic drain body updates loop state per match arm
(`…__body__selected__continue__state`, `…__body__gap__continue__state`); the
recognizer must select the arm that actually ran in the final iteration, keep
supporting the single `…__body__state` shape, ignore skipped arms, and fail
fast (not silently fall back to the iteration-entry frame) when candidates are
ambiguous.
"""

from __future__ import annotations

import pytest

from orchestrator.workflow.loops import LoopExecutor, LoopStateIntegrityError


FRAME = {
    "status": "running",
    "state__items-processed": 3,
    "state__progress-report-path": "artifacts/work/item-3-progress.md",
}


def _exhaustion(frame, iteration_state, iteration=3):
    executor = LoopExecutor.__new__(LoopExecutor)
    return executor._exhaustion_frame_artifacts(
        frame_artifacts=frame,
        iteration_state=iteration_state,
        current_iteration=iteration,
    )


def test_single_body_state_step_snapshot_still_recognized() -> None:
    iteration_state = {
        "loop__body__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 4,
                "state__progress-report-path": "artifacts/work/item-4-progress.md",
            },
        }
    }

    artifacts = _exhaustion(FRAME, iteration_state)

    assert artifacts["state__progress-report-path"] == "artifacts/work/item-4-progress.md"


def test_branched_arm_state_step_snapshot_selected() -> None:
    iteration_state = {
        "loop__body__selected__continue__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 4,
                "state__progress-report-path": "artifacts/work/item-4-progress.md",
            },
        }
    }

    artifacts = _exhaustion(FRAME, iteration_state)

    assert artifacts["state__items-processed"] == 4
    assert artifacts["state__progress-report-path"] == "artifacts/work/item-4-progress.md"


def test_arm_update_preferred_over_iteration_entry_binding() -> None:
    # The generic drain body carries BOTH the executed arm's state update and
    # the `…__body__state` iteration-entry binding (the stale value that the
    # pre-fix recognizer reported). The update must win.
    iteration_state = {
        "loop__body__selected__continue__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 4,
                "state__progress-report-path": "artifacts/work/item-4-progress.md",
            },
        },
        "loop__body__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 3,
                "state__progress-report-path": "artifacts/work/item-3-progress.md",
            },
        },
    }

    artifacts = _exhaustion(FRAME, iteration_state)

    assert artifacts["state__items-processed"] == 4
    assert artifacts["state__progress-report-path"] == "artifacts/work/item-4-progress.md"


def test_skipped_arm_state_step_ignored() -> None:
    iteration_state = {
        "loop__body__selected__continue__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 4,
                "state__progress-report-path": "artifacts/work/item-4-progress.md",
            },
        },
        "loop__body__gap__continue__state": {
            "status": "skipped",
            "skipped": True,
        },
    }

    artifacts = _exhaustion(FRAME, iteration_state)

    assert artifacts["state__progress-report-path"] == "artifacts/work/item-4-progress.md"


def test_ambiguous_executed_state_steps_fail_fast() -> None:
    iteration_state = {
        "loop__body__selected__continue__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 4,
                "state__progress-report-path": "artifacts/work/item-4-progress.md",
            },
        },
        "loop__body__gap__continue__state": {
            "status": "completed",
            "artifacts": {
                "state__items-processed": 9,
                "state__progress-report-path": "artifacts/work/item-9-progress.md",
            },
        },
    }

    with pytest.raises(LoopStateIntegrityError, match="ambiguous"):
        _exhaustion(FRAME, iteration_state)


def test_no_state_step_falls_back_to_entry_frame() -> None:
    iteration_state = {
        "loop__body__condition": {"status": "completed", "artifacts": {"ok": True}}
    }

    artifacts = _exhaustion(FRAME, iteration_state)

    assert artifacts == dict(FRAME)


def test_zero_iterations_uses_entry_frame() -> None:
    artifacts = _exhaustion(FRAME, {}, iteration=0)

    assert artifacts == dict(FRAME)
