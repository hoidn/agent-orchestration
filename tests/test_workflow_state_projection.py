"""Characterization tests for IR-to-state compatibility projection tables."""

from dataclasses import (
    FrozenInstanceError,
)

import pytest


def test_resume_scope_path_snapshots_mutable_call_frame_input() -> None:
    from orchestrator.workflow.resume_projection_integrity import ResumeScopePath

    source_frame_ids = ["frame-one"]
    scope_path = ResumeScopePath(
        root_workflow_file="workflow.yaml",
        call_frame_ids=source_frame_ids,
    )

    source_frame_ids.append("frame-two")

    assert scope_path.call_frame_ids == ("frame-one",)
    assert scope_path.as_context() == [
        {"kind": "root", "workflow_file": "workflow.yaml"},
        {"kind": "call_frame", "frame_id": "frame-one"},
    ]
    with pytest.raises(FrozenInstanceError):
        scope_path.call_frame_ids = ("replacement",)
