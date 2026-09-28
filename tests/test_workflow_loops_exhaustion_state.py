"""Unit coverage for repeat_until exhaustion progress integrity."""

from __future__ import annotations

import pytest

from orchestrator.workflow.state_projection import (
    IterationStepKeyProjection,
    ResumeProjectionValidationError,
    _validated_repeat_until_iterations,
)


def test_failed_exhaustion_projection_keys_on_generic_type_not_optional_code() -> None:
    projection = IterationStepKeyProjection(
        node_id="root.loop",
        frame_key="Loop",
        max_iterations=2,
    )
    progress = {
        "current_iteration": None,
        "completed_iterations": [0, 1],
        "condition_evaluated_for_iteration": 1,
        "last_condition_result": False,
    }

    assert _validated_repeat_until_iterations(
        projection,
        progress,
        {
            "status": "failed",
            "error": {
                "type": "repeat_until_iterations_exhausted",
                "code": "bounded_traversal_cap_exceeded",
            },
        },
    ) == (0, 1)

    with pytest.raises(
        ResumeProjectionValidationError,
        match="requires the terminal exhaustion error",
    ):
        _validated_repeat_until_iterations(
            projection,
            progress,
            {
                "status": "failed",
                "error": {
                    "type": "bounded_traversal_cap_exceeded",
                    "code": "bounded_traversal_cap_exceeded",
                },
            },
        )
