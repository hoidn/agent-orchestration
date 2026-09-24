"""Runtime suspension and reply consumption for request-input nodes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from orchestrator.state import StateManager
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.human_input import get_human_input, submit_human_input
from orchestrator.workflow.lowering import build_loaded_workflow_bundle


def _bundle(workflow_path: Path, question: dict[str, str]):
    inputs = {"question": {"type": "string"}} if "ref" in question else {}
    surface = elaborate_surface_workflow(
        {
            "version": "2.32",
            "name": "human-input-runtime",
            "inputs": inputs,
            "steps": [{"name": "Ask", "request_input": {"question": question}}],
        },
        workflow_path=workflow_path,
        imported_bundles={},
    )
    assert surface is not None
    return build_loaded_workflow_bundle(surface, imports={})


def _manager(
    tmp_path: Path,
    workflow_path: Path,
    *,
    bound_inputs: dict[str, str] | None = None,
) -> StateManager:
    workflow_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="human-input-runtime")
    manager.initialize(str(workflow_path), bound_inputs=bound_inputs)
    return manager


def _bundle_with_failing_follow_up(workflow_path: Path):
    surface = elaborate_surface_workflow(
        {
            "version": "2.32",
            "name": "human-input-durable-reply",
            "steps": [
                {
                    "name": "Ask",
                    "request_input": {"question": {"literal": "Continue?"}},
                },
                {
                    "name": "FailAfterReply",
                    "assert": {
                        "equals": {"left": "expected", "right": "actual"},
                    },
                },
            ],
        },
        workflow_path=workflow_path,
        imported_bundles={},
    )
    assert surface is not None
    return build_loaded_workflow_bundle(surface, imports={})


def test_literal_request_suspends_then_answered_resume_publishes_reply(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle(workflow_path, {"literal": "Continue?"})
    manager = _manager(tmp_path, workflow_path)
    executor = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0)

    ask = executor._runtime_step_by_name("Ask")
    assert executor._projected_discriminant_name_for_runtime_step(ask) == "variant"
    assert executor._artifact_contract_for_runtime_step(ask, "variant") == {
        "type": "enum", "allowed": ["ANSWERED", "CANCELLED"],
        "projection": {
            "projection_class": "union_workflow_boundary",
            "return_kind": "union", "union_output_group": "human_reply",
            "discriminant_output": "variant", "field_role": "discriminant",
            "active_variants": ["ANSWERED", "CANCELLED"],
        },
    }
    suspended = executor.execute()

    assert suspended["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    assert request["question"] == "Continue?"
    assert request["status"] == "pending"

    waiting_manager = StateManager(tmp_path, run_id="human-input-runtime")
    waiting_manager.load()
    still_waiting = WorkflowExecutor(
        bundle, tmp_path, waiting_manager, retry_delay_ms=0,
    ).execute(resume=True)
    assert still_waiting["status"] == "suspended"
    assert get_human_input(manager.run_root) == request
    assert waiting_manager.load().step_visits == {"Ask": 1}

    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "ANSWERED", "text": "yes"},
    )
    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["steps"]["Ask"]["artifacts"] == {
        "variant": "ANSWERED", "text": "yes",
    }
    assert get_human_input(manager.run_root)["status"] == "consumed"


def test_literal_request_cancellation_publishes_only_the_active_variant(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle(workflow_path, {"literal": "Continue?"})
    manager = _manager(tmp_path, workflow_path)

    WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()
    request = get_human_input(manager.run_root)
    assert request is not None
    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "CANCELLED"},
    )
    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["steps"]["Ask"]["artifacts"] == {"variant": "CANCELLED"}
    assert resumed_manager.load().step_visits == {"Ask": 1}


def test_top_level_request_input_failure_is_persisted(
    tmp_path: Path,
) -> None:
    """A runtime question type failure follows the ordinary failed-step path."""

    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle(workflow_path, {"ref": "inputs.question"})
    manager = _manager(tmp_path, workflow_path, bound_inputs={"question": 7})

    failed = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()

    assert failed["status"] == "failed"
    assert failed["steps"]["Ask"]["status"] == "failed"
    assert failed["steps"]["Ask"]["error"]["context"]["reason"] == (
        "request_input_question_not_string"
    )


@pytest.mark.parametrize(
    ("reply", "expected_artifacts"),
    (
        ({"variant": "ANSWERED", "text": "yes"}, {"variant": "ANSWERED", "text": "yes"}),
        ({"variant": "CANCELLED"}, {"variant": "CANCELLED"}),
    ),
)
def test_completed_human_reply_survives_downstream_failure_without_reasking(
    tmp_path: Path,
    reply: dict[str, str],
    expected_artifacts: dict[str, str],
) -> None:
    """A later failure cannot turn a committed direct reply into a new request."""

    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle_with_failing_follow_up(workflow_path)
    manager = _manager(tmp_path, workflow_path)

    assert WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    submit_human_input(manager.run_root, request["request_id"], reply)

    first_resume_manager = StateManager(tmp_path, run_id="human-input-runtime")
    first_resume_manager.load()
    failed = WorkflowExecutor(
        bundle, tmp_path, first_resume_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert failed["status"] == "failed"
    assert failed["steps"]["Ask"]["artifacts"] == expected_artifacts
    assert get_human_input(manager.run_root)["status"] == "consumed"

    second_resume_manager = StateManager(tmp_path, run_id="human-input-runtime")
    second_resume_manager.load()
    retried = WorkflowExecutor(
        bundle, tmp_path, second_resume_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert retried["status"] == "failed"
    assert retried["steps"]["Ask"]["artifacts"] == expected_artifacts
    assert get_human_input(manager.run_root)["status"] == "consumed"
    assert second_resume_manager.load().step_visits["Ask"] == 1


def test_direct_human_reply_uses_its_atomic_write_not_generic_persistence(
    tmp_path: Path,
) -> None:
    """The consumed reply publishes once, then emits one post-commit checkpoint hook."""

    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle_with_failing_follow_up(workflow_path)
    manager = _manager(tmp_path, workflow_path)
    assert WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "ANSWERED", "text": "yes"},
    )

    persisted_steps: list[str] = []
    checkpoint_steps: list[str] = []
    original_persist = WorkflowExecutor._persist_step_result
    original_checkpoint = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit

    def track_persist(self, state, step_name, step, result):
        persisted_steps.append(step_name)
        return original_persist(self, state, step_name, step, result)

    def track_checkpoint(self, state, step_name, step, finalized):
        checkpoint_steps.append(step_name)
        return original_checkpoint(self, state, step_name, step, finalized)

    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    with patch.object(WorkflowExecutor, "_persist_step_result", track_persist), patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        track_checkpoint,
    ):
        result = WorkflowExecutor(
            bundle, tmp_path, resumed_manager, retry_delay_ms=0,
        ).execute(resume=True)

    assert result["status"] == "failed"
    assert persisted_steps == ["FailAfterReply"]
    assert checkpoint_steps.count("Ask") == 1
    assert get_human_input(manager.run_root)["status"] == "consumed"


def test_interruption_after_consumed_reply_before_checkpoint_never_reasks(
    tmp_path: Path,
) -> None:
    """A crash in the post-consumption hook recovers the committed reply, not a new UUID."""

    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle_with_failing_follow_up(workflow_path)
    manager = _manager(tmp_path, workflow_path)
    assert WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "CANCELLED"},
    )

    class AfterConsumptionInterruption(BaseException):
        pass

    def interrupt_before_checkpoint(self, state, step_name, step, finalized):
        if step_name == "Ask":
            raise AfterConsumptionInterruption

    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    with patch.object(
        WorkflowExecutor,
        "_emit_lexical_checkpoint_shadow_after_step_commit",
        interrupt_before_checkpoint,
    ), pytest.raises(AfterConsumptionInterruption):
        WorkflowExecutor(
            bundle, tmp_path, resumed_manager, retry_delay_ms=0,
        ).execute(resume=True)

    after_interruption = StateManager(tmp_path, run_id="human-input-runtime")
    persisted = after_interruption.load()
    assert persisted.steps["Ask"]["artifacts"] == {"variant": "CANCELLED"}
    assert get_human_input(manager.run_root)["status"] == "consumed"

    recovered = WorkflowExecutor(
        bundle, tmp_path, after_interruption, retry_delay_ms=0,
    ).execute(resume=True)

    assert recovered["status"] == "failed"
    assert recovered["steps"]["Ask"]["artifacts"] == {"variant": "CANCELLED"}
    assert get_human_input(manager.run_root)["status"] == "consumed"
    assert after_interruption.load().step_visits["Ask"] == 1


def test_reference_question_uses_the_bound_input_once_before_suspension(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle(workflow_path, {"ref": "inputs.question"})
    manager = _manager(
        tmp_path,
        workflow_path,
        bound_inputs={"question": "What changed?"},
    )

    suspended = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()

    assert suspended["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    assert request["question"] == "What changed?"
    assert manager.load().bound_inputs == {"question": "What changed?"}


def test_pending_resume_rejects_a_stale_leaf_cursor(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.orc"
    bundle = _bundle(workflow_path, {"literal": "Continue?"})
    manager = _manager(tmp_path, workflow_path)

    WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()
    assert manager.state is not None
    manager.state.current_step["visit_count"] = 2
    manager._write_state()

    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    with pytest.raises(ValueError, match="human input resume leaf cursor is stale"):
        WorkflowExecutor(bundle, tmp_path, resumed_manager, retry_delay_ms=0).execute(
            resume=True,
        )


def test_for_each_request_resumes_the_same_iteration_without_reasking(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.orc"
    surface = elaborate_surface_workflow(
        {
            "version": "2.32",
            "name": "human-input-loop",
            "steps": [
                {
                    "name": "Each",
                    "for_each": {
                        "items": ["only"],
                        "steps": [
                            {
                                "name": "Ask",
                                "request_input": {
                                    "question": {"literal": "Continue?"},
                                },
                            },
                        ],
                    },
                },
            ],
        },
        workflow_path=workflow_path,
        imported_bundles={},
    )
    assert surface is not None
    bundle = build_loaded_workflow_bundle(surface, imports={})
    manager = _manager(tmp_path, workflow_path)

    suspended = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()

    assert suspended["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    assert request["loop_iteration"] == {
        "loop_step_id": "root.each", "iteration": 0, "kind": "for_each",
    }

    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "ANSWERED", "text": "yes"},
    )
    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["steps"]["Each[0].Ask"]["artifacts"] == {
        "variant": "ANSWERED", "text": "yes",
    }
    assert get_human_input(manager.run_root)["status"] == "consumed"


def test_for_each_replaces_a_consumed_request_on_the_next_iteration(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "workflow.orc"
    surface = elaborate_surface_workflow(
        {
            "version": "2.32",
            "name": "human-input-loop-sequence",
            "steps": [
                {
                    "name": "Each",
                    "for_each": {
                        "items": ["first", "second"],
                        "steps": [
                            {
                                "name": "Ask",
                                "request_input": {
                                    "question": {"literal": "Continue?"},
                                },
                            },
                        ],
                    },
                },
            ],
        },
        workflow_path=workflow_path,
        imported_bundles={},
    )
    assert surface is not None
    bundle = build_loaded_workflow_bundle(surface, imports={})
    manager = _manager(tmp_path, workflow_path)

    WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()
    first = get_human_input(manager.run_root)
    assert first is not None
    submit_human_input(
        manager.run_root, first["request_id"], {"variant": "ANSWERED", "text": "one"},
    )
    first_resume_manager = StateManager(tmp_path, run_id="human-input-runtime")
    first_resume_manager.load()
    second_wait = WorkflowExecutor(
        bundle, tmp_path, first_resume_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert second_wait["status"] == "suspended"
    second = get_human_input(manager.run_root)
    assert second is not None
    assert second["status"] == "pending"
    assert second["request_id"] != first["request_id"]
    assert second["runtime_step_id"] != first["runtime_step_id"]
    submit_human_input(manager.run_root, second["request_id"], {"variant": "CANCELLED"})
    final_manager = StateManager(tmp_path, run_id="human-input-runtime")
    final_manager.load()
    completed = WorkflowExecutor(
        bundle, tmp_path, final_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert completed["status"] == "completed"
    assert completed["steps"]["Each[0].Ask"]["artifacts"] == {
        "variant": "ANSWERED", "text": "one",
    }
    assert completed["steps"]["Each[1].Ask"]["artifacts"] == {
        "variant": "CANCELLED",
    }


def test_imported_request_resumes_the_existing_call_frame(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-child",
                "steps": [
                    {
                        "name": "Ask",
                        "request_input": {
                            "question": {"literal": "Continue?"},
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-parent",
                "imports": {"child": "child.yaml"},
                "steps": [{"name": "RunChild", "call": "child"}],
            },
        ),
        encoding="utf-8",
    )
    child_surface = elaborate_surface_workflow(
        json.loads(child_path.read_text(encoding="utf-8")),
        workflow_path=child_path,
        imported_bundles={},
    )
    assert child_surface is not None
    child_bundle = build_loaded_workflow_bundle(child_surface, imports={})
    parent_surface = elaborate_surface_workflow(
        json.loads(workflow_path.read_text(encoding="utf-8")),
        workflow_path=workflow_path,
        imported_bundles={"child": child_bundle},
    )
    assert parent_surface is not None
    bundle = build_loaded_workflow_bundle(parent_surface, imports={"child": child_bundle})
    manager = _manager(tmp_path, workflow_path)

    suspended = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()

    assert suspended["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    assert request["resume_scope"]["call_frame_ids"] == ["root.runchild::visit::1"]
    waiting_manager = StateManager(tmp_path, run_id="human-input-runtime")
    waiting_manager.load()
    still_waiting = WorkflowExecutor(
        bundle, tmp_path, waiting_manager, retry_delay_ms=0,
    ).execute(resume=True)
    assert still_waiting["status"] == "suspended"
    assert get_human_input(manager.run_root) == request
    waiting_state = waiting_manager.load().to_dict()
    assert waiting_state["step_visits"] == {"RunChild": 1}
    assert waiting_state["call_frames"]["root.runchild::visit::1"]["state"]["step_visits"] == {
        "Ask": 1,
    }
    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "ANSWERED", "text": "yes"},
    )
    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    frame = resumed["call_frames"]["root.runchild::visit::1"]
    assert frame["state"]["steps"]["Ask"]["artifacts"] == {
        "variant": "ANSWERED", "text": "yes",
    }
    assert get_human_input(manager.run_root)["status"] == "consumed"


def test_imported_pending_resume_rejects_a_stale_ancestor_cursor(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        json.dumps(
                {
                    "version": "2.32",
                    "name": "human-input-child",
                    "inputs": {"question": {"type": "string"}},
                    "steps": [{"name": "Ask", "request_input": {"question": {"ref": "inputs.question"}}}],
            },
        ),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-parent",
                "imports": {"child": "child.yaml"},
                "steps": [{"name": "RunChild", "call": "child", "with": {"question": "Continue?"}}],
            },
        ),
        encoding="utf-8",
    )
    child_surface = elaborate_surface_workflow(
        json.loads(child_path.read_text(encoding="utf-8")),
        workflow_path=child_path,
        imported_bundles={},
    )
    assert child_surface is not None
    child_bundle = build_loaded_workflow_bundle(child_surface, imports={})
    parent_surface = elaborate_surface_workflow(
        json.loads(workflow_path.read_text(encoding="utf-8")),
        workflow_path=workflow_path,
        imported_bundles={"child": child_bundle},
    )
    assert parent_surface is not None
    bundle = build_loaded_workflow_bundle(parent_surface, imports={"child": child_bundle})
    manager = _manager(tmp_path, workflow_path)

    WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()
    assert manager.state is not None
    manager.state.current_step["visit_count"] = 2
    manager.state.step_visits["RunChild"] = 2
    manager._write_state()

    stale_frame = manager.state.call_frames["root.runchild::visit::1"]
    assert not WorkflowExecutor._human_input_call_frame_reached(
        bundle,
        manager.state.to_dict(),
        stale_frame,
    )

    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    with pytest.raises(ValueError, match="human input resume ancestor cursor is stale"):
        WorkflowExecutor(bundle, tmp_path, resumed_manager, retry_delay_ms=0).execute(
            resume=True,
        )


def test_pending_imported_request_revalidates_nested_call_metadata(
    tmp_path: Path,
) -> None:
    """Waiting does not skip the usual child checksum or input checks."""

    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-child",
                "inputs": {"question": {"type": "string"}},
                "steps": [{"name": "Ask", "request_input": {"question": {"ref": "inputs.question"}}}],
            },
        ),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-parent",
                "imports": {"child": "child.yaml"},
                "steps": [{"name": "RunChild", "call": "child", "with": {"question": "Continue?"}}],
            },
        ),
        encoding="utf-8",
    )
    child_surface = elaborate_surface_workflow(
        json.loads(child_path.read_text(encoding="utf-8")),
        workflow_path=child_path,
        imported_bundles={},
    )
    assert child_surface is not None
    child_bundle = build_loaded_workflow_bundle(child_surface, imports={})
    parent_surface = elaborate_surface_workflow(
        json.loads(workflow_path.read_text(encoding="utf-8")),
        workflow_path=workflow_path,
        imported_bundles={"child": child_bundle},
    )
    assert parent_surface is not None
    bundle = build_loaded_workflow_bundle(parent_surface, imports={"child": child_bundle})
    manager = _manager(tmp_path, workflow_path)

    assert WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()["status"] == "suspended"
    assert manager.state is not None
    frame = manager.state.call_frames["root.runchild::visit::1"]
    child_state = frame["state"]
    original_checksum = child_state["workflow_checksum"]
    child_state["workflow_checksum"] = "sha256:" + "0" * 64
    manager._write_state()

    checksum_manager = StateManager(tmp_path, run_id="human-input-runtime")
    checksum_manager.load()
    with pytest.raises(ValueError, match="human input resume nested call validation failed"):
        WorkflowExecutor(bundle, tmp_path, checksum_manager, retry_delay_ms=0).execute(
            resume=True,
        )

    assert manager.state is not None
    manager.state.call_frames["root.runchild::visit::1"]["state"]["workflow_checksum"] = original_checksum
    manager.state.call_frames["root.runchild::visit::1"]["bound_inputs"] = {"question": "changed"}
    manager._write_state()

    inputs_manager = StateManager(tmp_path, run_id="human-input-runtime")
    inputs_manager.load()
    with pytest.raises(ValueError, match="human input resume nested call validation failed"):
        WorkflowExecutor(bundle, tmp_path, inputs_manager, retry_delay_ms=0).execute(
            resume=True,
        )


def test_imported_loop_request_resumes_the_reached_call_and_iteration(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "child.yaml"
    child_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-child",
                "inputs": {"question": {"type": "string"}},
                "steps": [
                    {
                        "name": "Ask",
                        "request_input": {"question": {"ref": "inputs.question"}},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-parent",
                "imports": {"child": "child.yaml"},
                "artifacts": {"question": {"kind": "scalar", "type": "string"}},
                "steps": [
                    {
                        "name": "Each",
                        "for_each": {
                            "items": ["first", "second"],
                            "steps": [
                                {
                                    "name": "SetQuestion",
                                    "set_scalar": {
                                        "artifact": "question",
                                        "value": "loop-local",
                                    },
                                },
                                {
                                    "name": "RunChild",
                                    "call": "child",
                                    "with": {
                                        "question": {
                                            "ref": "self.steps.SetQuestion.artifacts.question",
                                        },
                                    },
                                },
                            ],
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    child_surface = elaborate_surface_workflow(
        json.loads(child_path.read_text(encoding="utf-8")),
        workflow_path=child_path,
        imported_bundles={},
    )
    assert child_surface is not None
    child_bundle = build_loaded_workflow_bundle(child_surface, imports={})
    parent_surface = elaborate_surface_workflow(
        json.loads(workflow_path.read_text(encoding="utf-8")),
        workflow_path=workflow_path,
        imported_bundles={"child": child_bundle},
    )
    assert parent_surface is not None
    bundle = build_loaded_workflow_bundle(parent_surface, imports={"child": child_bundle})
    manager = _manager(tmp_path, workflow_path)

    suspended = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()

    assert suspended["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    assert request["question"] == "loop-local"
    assert request["loop_iteration"] is None
    assert request["resume_scope"]["call_frame_ids"] == [
        "root.each#0.runchild::visit::1",
    ]
    assert manager.state is not None
    manager.state.for_each["Each"].current_index = 1
    manager._write_state()
    stale_manager = StateManager(tmp_path, run_id="human-input-runtime")
    stale_manager.load()
    stale_frame = stale_manager.state.call_frames["root.each#0.runchild::visit::1"]
    assert not WorkflowExecutor._human_input_call_frame_reached(
        bundle, stale_manager.state.to_dict(), stale_frame,
    )
    stale_resume = WorkflowExecutor(
        bundle, tmp_path, stale_manager, retry_delay_ms=0,
    ).execute(resume=True)
    assert stale_resume["status"] == "failed"
    manager.state.for_each["Each"].current_index = 0
    manager._write_state()
    submit_human_input(
        manager.run_root,
        request["request_id"],
        {"variant": "CANCELLED"},
    )
    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert resumed["status"] == "suspended"
    second = get_human_input(manager.run_root)
    assert second is not None and second["request_id"] != request["request_id"]
    submit_human_input(manager.run_root, second["request_id"], {"variant": "CANCELLED"})
    final_manager = StateManager(tmp_path, run_id="human-input-runtime")
    final_manager.load()
    completed = WorkflowExecutor(
        bundle, tmp_path, final_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert completed["status"] == "completed"
    frame = completed["call_frames"]["root.each#0.runchild::visit::1"]
    assert frame["state"]["steps"]["Ask"]["artifacts"] == {"variant": "CANCELLED"}
    assert final_manager.load().step_visits == {"Each": 1}


def test_two_level_imported_request_resumes_through_each_call_cursor(
    tmp_path: Path,
) -> None:
    leaf_path = tmp_path / "leaf.yaml"
    middle_path = tmp_path / "middle.yaml"
    workflow_path = tmp_path / "workflow.yaml"
    leaf_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-leaf",
                "inputs": {"question": {"type": "string"}},
                "steps": [
                    {
                        "name": "Ask",
                        "request_input": {"question": {"ref": "inputs.question"}},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    middle_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-middle",
                "imports": {"leaf": "leaf.yaml"},
                "artifacts": {"question": {"kind": "scalar", "type": "string"}},
                "steps": [
                    {
                        "name": "SetQuestion",
                        "set_scalar": {"artifact": "question", "value": "middle-local"},
                    },
                    {
                        "name": "RunLeaf",
                        "call": "leaf",
                        "with": {
                            "question": {
                                "ref": "root.steps.SetQuestion.artifacts.question",
                            },
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    workflow_path.write_text(
        json.dumps(
            {
                "version": "2.32",
                "name": "human-input-root",
                "imports": {"middle": "middle.yaml"},
                "steps": [{"name": "RunMiddle", "call": "middle"}],
            },
        ),
        encoding="utf-8",
    )
    leaf_surface = elaborate_surface_workflow(
        json.loads(leaf_path.read_text(encoding="utf-8")),
        workflow_path=leaf_path,
        imported_bundles={},
    )
    assert leaf_surface is not None
    leaf_bundle = build_loaded_workflow_bundle(leaf_surface, imports={})
    middle_surface = elaborate_surface_workflow(
        json.loads(middle_path.read_text(encoding="utf-8")),
        workflow_path=middle_path,
        imported_bundles={"leaf": leaf_bundle},
    )
    assert middle_surface is not None
    middle_bundle = build_loaded_workflow_bundle(middle_surface, imports={"leaf": leaf_bundle})
    root_surface = elaborate_surface_workflow(
        json.loads(workflow_path.read_text(encoding="utf-8")),
        workflow_path=workflow_path,
        imported_bundles={"middle": middle_bundle},
    )
    assert root_surface is not None
    bundle = build_loaded_workflow_bundle(root_surface, imports={"middle": middle_bundle})
    manager = _manager(tmp_path, workflow_path)

    suspended = WorkflowExecutor(bundle, tmp_path, manager, retry_delay_ms=0).execute()

    assert suspended["status"] == "suspended"
    request = get_human_input(manager.run_root)
    assert request is not None
    assert request["resume_scope"]["call_frame_ids"] == [
        "root.runmiddle::visit::1",
        "root.runmiddle::visit::1.root.runleaf::visit::1",
    ]
    assert request["question"] == "middle-local"
    submit_human_input(manager.run_root, request["request_id"], {"variant": "ANSWERED", "text": "yes"})
    resumed_manager = StateManager(tmp_path, run_id="human-input-runtime")
    resumed_manager.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_manager, retry_delay_ms=0,
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    middle = resumed["call_frames"]["root.runmiddle::visit::1"]["state"]
    leaf = middle["call_frames"]["root.runmiddle::visit::1.root.runleaf::visit::1"]["state"]
    assert leaf["steps"]["Ask"]["artifacts"] == {"variant": "ANSWERED", "text": "yes"}
