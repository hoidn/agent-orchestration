from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.run_lock import RunAlreadyActiveError, run_writer_lock
from orchestrator.state import ForEachState, RunState, StateManager, StepResult
from orchestrator.workflow.human_input import (
    consume_human_input,
    get_human_input,
    record_human_input,
    submit_human_input,
    validate_human_input_record,
)
from orchestrator.workflow.call_frame_state import (
    _CallFrameStateManager,
    _path_safe_frame_scope_token,
    load_existing_call_frame_read_only,
)
from orchestrator.workflow.resume_projection_integrity import ResumeScopePath
from orchestrator.workflow.state_projection import IterationStepKeyProjection


def _pending_record() -> dict[str, object]:
    return {
        "request_id": "00000000-0000-4000-8000-000000000001",
        "resume_scope": {"root_workflow_file": "workflow.yaml", "call_frame_ids": []},
        "runtime_step_id": "request",
        "enclosing_step": {
            "step_name": "request", "step_id": "request", "visit_count": 1,
        },
        "loop_iteration": None,
        "question": "Continue?",
        "status": "pending",
    }


def _manager(tmp_path: Path, *, custom_root: bool = False) -> StateManager:
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text("version: 1\nsteps: []\n", encoding="utf-8")
    state_dir = tmp_path / "durable-runs" if custom_root else None
    manager = StateManager(tmp_path, run_id="human", state_dir=state_dir)
    manager.initialize("workflow.yaml")
    assert manager.state is not None
    manager.state.current_step = {
        "name": "request", "step_id": "request", "visit_count": 1,
    }
    manager.state.step_visits = {"request": 1}
    manager._write_state()
    return manager


def _actual_child_manager(root: StateManager) -> _CallFrameStateManager:
    assert root.state is not None
    frame_id = "frame"
    child_root = root.run_root / "call_frames" / _path_safe_frame_scope_token(frame_id)
    child_state = RunState(
        schema_version="2.1", run_id=root.run_id, workflow_file="child.yaml",
        workflow_checksum="checksum", started_at="now", updated_at="now", status="running",
        run_root=str(child_root), step_visits={"request": 1},
        current_step={"name": "request", "step_id": "request", "visit_count": 1},
    )
    child = object.__new__(_CallFrameStateManager)
    child.parent_manager = root
    child.frame_id = frame_id
    child.run_id = root.run_id
    child.workspace = root.workspace
    child.run_root = child_root
    child.state = child_state
    child.resume_scope_path = ResumeScopePath.root("workflow.yaml").child(frame_id)
    root.state.call_frames[frame_id] = {
        "call_frame_id": frame_id,
        "state": child_state.to_dict(),
    }
    root._write_state()
    return child


def test_human_input_record_is_closed_and_pending_omits_reply() -> None:
    record = _pending_record()
    assert validate_human_input_record(record) == record
    with pytest.raises(ValueError):
        validate_human_input_record({**record, "reply": None})
    with pytest.raises(ValueError):
        validate_human_input_record({**record, "extra": True})
    for reply in (
        {"variant": "ANSWERED"},
        {"variant": "ANSWERED", "text": 0},
        {"variant": "CANCELLED", "text": "unexpected"},
        {"variant": "UNKNOWN"},
    ):
        with pytest.raises(ValueError):
            validate_human_input_record({**record, "status": "answered", "reply": reply})


def test_record_query_submit_and_idempotency_use_root_record(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    pending = record_human_input(
        manager,
        runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None,
        question="",
    )
    assert pending["status"] == "pending"
    assert "reply" not in pending
    assert manager.state is not None and manager.state.status == "suspended"
    assert get_human_input(manager.run_root) == pending
    assert record_human_input(
        manager,
        runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None,
        question="",
    ) == pending

    answered = submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "ANSWERED", "text": ""}
    )
    assert answered["status"] == "answered"
    assert answered["reply"] == {"variant": "ANSWERED", "text": ""}
    manager.load()
    assert record_human_input(
        manager,
        runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None,
        question="",
    ) == answered
    assert StateManager(tmp_path, run_id="human").load().status == "suspended"
    assert submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "ANSWERED", "text": ""}
    ) == answered
    with pytest.raises(ValueError, match="conflicts"):
        submit_human_input(
            manager.run_root, pending["request_id"], {"variant": "CANCELLED"}
        )


def test_submit_supports_existing_custom_state_root(tmp_path: Path) -> None:
    manager = _manager(tmp_path, custom_root=True)
    pending = record_human_input(
        manager,
        runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None,
        question="Continue?",
    )
    assert submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "CANCELLED"}
    )["status"] == "answered"


def test_run_state_omits_absent_human_input_and_validates_present_value() -> None:
    state = RunState(
        schema_version="2.1", run_id="run", workflow_file="workflow.yaml",
        workflow_checksum="checksum", started_at="now", updated_at="now", status="running",
    )
    assert "human_input" not in state.to_dict()
    state.human_input = _pending_record()
    assert RunState.from_dict(state.to_dict()).human_input == _pending_record()


def test_root_scoped_mutation_passes_the_root_once(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    reached: list[RunState] = []

    manager._mutate_scoped_state(
        ResumeScopePath.root("workflow.yaml"),
        commit_guard=lambda _leaf: True,
        scoped_mutation=lambda _root, chain: reached.extend(chain),
    )

    assert reached == [manager.state]


def test_call_frame_state_refuses_root_owned_human_input() -> None:
    state = RunState(
        schema_version="2.1", run_id="run", workflow_file="workflow.yaml",
        workflow_checksum="checksum", started_at="now", updated_at="now", status="running",
        human_input=_pending_record(),
    )
    with pytest.raises(ValueError, match="root-owned"):
        load_existing_call_frame_read_only({"state": state.to_dict()})


def test_consumed_identity_never_reuses_a_new_question(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    pending = record_human_input(
        manager,
        runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None,
        question="first",
    )
    submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "CANCELLED"}
    )
    assert manager.state is not None
    manager.load()
    manager.state.human_input = {
        **get_human_input(manager.run_root), "status": "consumed",
    }
    manager._write_state()
    with pytest.raises(ValueError, match="no longer pending"):
        record_human_input(
            manager,
            runtime_step_id="request",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
            loop_iteration=None,
            question="changed",
        )


@pytest.mark.parametrize("request_id", [0, {}, []])
def test_invalid_request_id_type_is_a_value_error(request_id: object) -> None:
    record = _pending_record()
    record["request_id"] = request_id
    with pytest.raises(ValueError, match="request_id"):
        validate_human_input_record(record)


def test_nested_publication_keeps_child_running(tmp_path: Path) -> None:
    root = _manager(tmp_path)
    assert root.state is not None
    child_root = (
        root.run_root / "call_frames" / _path_safe_frame_scope_token("frame")
    )
    child = RunState(
        schema_version="2.1", run_id=root.run_id, workflow_file="child.yaml",
        workflow_checksum="checksum", started_at="now", updated_at="now", status="running",
        run_root=str(child_root), step_visits={"request": 1},
        current_step={"name": "request", "step_id": "request", "visit_count": 1},
    )
    root.state.call_frames["frame"] = {"call_frame_id": "frame", "state": child.to_dict()}
    root._write_state()
    nested = SimpleNamespace(
        parent_manager=root, frame_id="frame", run_id=root.run_id,
        workspace=root.workspace, run_root=child_root, state=child,
        resume_scope_path=ResumeScopePath.root("workflow.yaml").child("frame"),
    )

    record_human_input(
        nested, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None, question="nested",
    )

    assert root.state.status == "suspended"
    assert root.state.call_frames["frame"]["state"]["status"] == "running"
    assert child.status == "running"


def test_publication_write_failure_restores_or_reloads_authoritative_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path)
    before = manager.state.to_dict() if manager.state is not None else None
    original_write = manager._write_state

    def fail_before(*_args: object, **_kwargs: object) -> None:
        raise OSError("before replace")

    monkeypatch.setattr(manager, "_write_state", fail_before)
    with pytest.raises(OSError, match="before replace"):
        record_human_input(
            manager, runtime_step_id="request",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
            loop_iteration=None, question="failure",
        )
    assert manager.state is not None and manager.state.to_dict() == before

    def fail_after(*args: object, **kwargs: object) -> None:
        original_write(*args, **kwargs)
        raise OSError("after replace")

    monkeypatch.setattr(manager, "_write_state", fail_after)
    with pytest.raises(OSError, match="after replace"):
        record_human_input(
            manager, runtime_step_id="request",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
            loop_iteration=None, question="failure",
        )
    assert manager.state is not None and manager.state.human_input is not None
    assert get_human_input(manager.run_root) == manager.state.human_input


def test_submit_rejects_stale_reply_and_writer_collision(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    pending = record_human_input(
        manager, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None, question="collision",
    )
    with pytest.raises(ValueError):
        record_human_input(
            manager, runtime_step_id="request",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
            loop_iteration=None, question="changed",
        )
    manager.state.current_step["visit_count"] = 2
    manager.state.step_visits["request"] = 2
    manager._write_state()
    with pytest.raises(ValueError, match="outstanding"):
        record_human_input(
            manager, runtime_step_id="request",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 2},
            loop_iteration=None, question="second request",
        )
    assert get_human_input(manager.run_root) == pending
    with pytest.raises(ValueError, match="stale"):
        submit_human_input(
            manager.run_root, "00000000-0000-4000-8000-000000000099",
            {"variant": "CANCELLED"},
        )
    with run_writer_lock(manager.run_root):
        with pytest.raises(RunAlreadyActiveError):
            submit_human_input(
                manager.run_root, pending["request_id"], {"variant": "CANCELLED"}
            )


def test_publication_requires_exact_reached_visit_and_runtime_address(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(TimeoutError):
        record_human_input(
            manager, runtime_step_id="other",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
            loop_iteration=None, question="wrong runtime",
        )
    assert manager.state is not None
    manager.state.step_visits["request"] = 2
    manager._write_state()
    with pytest.raises(TimeoutError):
        record_human_input(
            manager, runtime_step_id="request",
            enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
            loop_iteration=None, question="wrong visit",
        )


def test_loop_publication_requires_the_active_exact_loop_progress(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.state is not None
    manager.state.current_step = {
        "name": "loop", "step_id": "loop-id", "visit_count": 2,
    }
    manager.state.step_visits = {"loop": 2}
    manager.state.for_each = {
        "loop": ForEachState(items=["item"], current_index=3),
    }
    manager._write_state()
    request = record_human_input(
        manager, runtime_step_id="loop-id#3.request",
        enclosing_step={"step_name": "loop", "step_id": "loop-id", "visit_count": 2},
        loop_iteration={"kind": "for_each", "loop_step_id": "loop-id", "iteration": 3},
        question="loop",
    )
    assert request["loop_iteration"]["iteration"] == 3


def test_consume_atomically_publishes_direct_answer_and_dataflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _manager(tmp_path)
    pending = record_human_input(
        manager, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None, question="answer",
    )
    submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "ANSWERED", "text": "yes"}
    )
    manager.load()
    commits = []
    original_write = manager._write_state

    def counted_write(*args, **kwargs):
        commits.append(manager.state.to_dict())
        original_write(*args, **kwargs)

    monkeypatch.setattr(manager, "_write_state", counted_write)
    committed = consume_human_input(
        manager, pending["request_id"], step_name="request",
        result=StepResult(
            status="completed", name="request", step_id="request",
            output={"variant": "ANSWERED", "text": "yes"},
        ),
        artifact_versions={"answer": [{"version": 1}]},
        artifact_consumes={"answer": {"version": 1}},
        private_artifact_versions={"private_answer": [{"version": 1}]},
        private_artifact_consumes={"private_answer": {"version": 1}},
    )
    assert committed.steps["request"].output == {"variant": "ANSWERED", "text": "yes"}
    assert committed.current_step is None
    assert committed.artifact_versions == {"answer": [{"version": 1}]}
    assert committed.artifact_consumes == {"answer": {"version": 1}}
    assert committed.private_artifact_versions == {"private_answer": [{"version": 1}]}
    assert committed.private_artifact_consumes == {"private_answer": {"version": 1}}
    assert len(commits) == 1
    assert commits[0]["human_input"]["status"] == "consumed"
    assert commits[0]["steps"]["request"]["output"] == {"variant": "ANSWERED", "text": "yes"}
    assert get_human_input(manager.run_root)["status"] == "consumed"
    assert StateManager(tmp_path, run_id="human").load().status == "running"
    with pytest.raises(ValueError, match="consumed"):
        consume_human_input(
            manager, pending["request_id"], step_name="request",
            result=StepResult(
                status="completed", name="request", step_id="request",
                output={"variant": "ANSWERED", "text": "yes"},
            ),
        )


def test_consume_rejects_pending_or_reply_mismatch_without_publication(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    pending = record_human_input(
        manager, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None, question="answer",
    )
    result = StepResult(
        status="completed", name="request", step_id="request",
        output={"variant": "CANCELLED"},
    )
    with pytest.raises(ValueError, match="answered"):
        consume_human_input(manager, pending["request_id"], step_name="request", result=result)
    submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "ANSWERED", "text": "yes"}
    )
    manager.load()
    with pytest.raises(ValueError, match="reply"):
        consume_human_input(manager, pending["request_id"], step_name="request", result=result)
    assert manager.state is not None and "request" not in manager.state.steps


@pytest.mark.parametrize("presentation_name", ["request", "Ask the user"])
def test_consume_places_loop_result_by_frame_key_not_runtime_id(tmp_path: Path, presentation_name: str) -> None:
    manager = _manager(tmp_path)
    assert manager.state is not None
    manager.state.current_step = {
        "name": "loop", "step_id": "loop-id", "visit_count": 2,
    }
    manager.state.step_visits = {"loop": 2}
    manager.state.for_each = {"loop": ForEachState(items=["item"], current_index=3)}
    manager._write_state()
    pending = record_human_input(
        manager, runtime_step_id="loop-id#3.request",
        enclosing_step={"step_name": "loop", "step_id": "loop-id", "visit_count": 2},
        loop_iteration={"kind": "for_each", "loop_step_id": "loop-id", "iteration": 3},
        question="answer",
    )
    submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "CANCELLED"}
    )
    manager.load()
    projection = IterationStepKeyProjection(
        node_id="loop-id", frame_key="loop",
        nested_presentation_keys={"node": presentation_name},
        nested_step_id_suffixes={"node": "request"},
    )
    with pytest.raises(ValueError):
        consume_human_input(
            manager, pending["request_id"], loop_name="loop", index=3, step_name="other",
            loop_projection=projection, nested_node_id="node",
            result=StepResult(
                status="completed", name="other", step_id="loop-id#3.request",
                output={"variant": "CANCELLED"},
            ),
        )
    committed = consume_human_input(
        manager, pending["request_id"], loop_name="loop", index=3, step_name=presentation_name,
        loop_projection=projection, nested_node_id="node",
        result=StepResult(
            status="completed", name=presentation_name, step_id="loop-id#3.request",
            output={"variant": "CANCELLED"},
        ),
    )
    assert committed.steps[f"loop[3].{presentation_name}"].output == {"variant": "CANCELLED"}
    assert committed.current_step["step_id"] == "loop-id"


def test_consume_places_repeat_until_result_by_frame_key(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.state is not None
    manager.state.current_step = {
        "name": "repeat", "step_id": "repeat-id", "visit_count": 2,
    }
    manager.state.step_visits = {"repeat": 2}
    manager.state.repeat_until = {"repeat": {"current_iteration": 4}}
    manager._write_state()
    pending = record_human_input(
        manager, runtime_step_id="repeat-id#4.request",
        enclosing_step={"step_name": "repeat", "step_id": "repeat-id", "visit_count": 2},
        loop_iteration={"kind": "repeat_until", "loop_step_id": "repeat-id", "iteration": 4},
        question="answer",
    )
    submit_human_input(
        manager.run_root, pending["request_id"], {"variant": "CANCELLED"}
    )
    manager.load()
    committed = consume_human_input(
        manager, pending["request_id"], loop_name="repeat", index=4, step_name="request",
        loop_projection=IterationStepKeyProjection(
            node_id="repeat-id", frame_key="repeat",
            nested_presentation_keys={"node": "request"},
            nested_step_id_suffixes={"node": "request"},
        ),
        nested_node_id="node",
        result=StepResult(
            status="completed", name="request", step_id="repeat-id#4.request",
            output={"variant": "CANCELLED"},
        ),
    )
    assert committed.steps["repeat[4].request"].output == {"variant": "CANCELLED"}


def test_nested_consume_write_failures_refresh_real_call_frame_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _manager(tmp_path)
    child = _actual_child_manager(root)
    pending = record_human_input(
        child, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None, question="nested",
    )
    submit_human_input(root.run_root, pending["request_id"], {"variant": "CANCELLED"})
    root.load()
    child._refresh_state_chain_from_root()
    original_write = root._write_state
    dataflow = {
        "artifact_versions": {"answer": [{"version": 1}]},
        "artifact_consumes": {"answer": {"version": 1}},
        "private_artifact_versions": {"private_answer": [{"version": 1}]},
        "private_artifact_consumes": {"private_answer": {"version": 1}},
    }

    def fail_before(*_args: object, **_kwargs: object) -> None:
        raise OSError("before replace")

    monkeypatch.setattr(root, "_write_state", fail_before)
    with pytest.raises(OSError, match="before replace"):
        consume_human_input(
            child, pending["request_id"], step_name="request",
            **dataflow,
            result=StepResult(
                status="completed", name="request", step_id="request",
                output={"variant": "CANCELLED"},
            ),
        )
    assert child.state.steps == {}
    for field in dataflow:
        assert getattr(child.state, field) == {}
    assert get_human_input(root.run_root)["status"] == "answered"

    def fail_after(*args: object, **kwargs: object) -> None:
        original_write(*args, **kwargs)
        raise OSError("after replace")

    monkeypatch.setattr(root, "_write_state", fail_after)
    with pytest.raises(OSError, match="after replace"):
        consume_human_input(
            child, pending["request_id"], step_name="request",
            **dataflow,
            result=StepResult(
                status="completed", name="request", step_id="request",
                output={"variant": "CANCELLED"},
            ),
        )
    assert child.state.steps["request"]["output"] == {"variant": "CANCELLED"}
    for field, expected in dataflow.items():
        assert getattr(child.state, field) == expected
    assert get_human_input(root.run_root)["status"] == "consumed"


def test_consumed_submission_is_idempotent_until_a_new_request_makes_it_stale(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    first = record_human_input(
        manager, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 1},
        loop_iteration=None, question="first",
    )
    reply = {"variant": "CANCELLED"}
    submit_human_input(manager.run_root, first["request_id"], reply)
    manager.load()
    consume_human_input(
        manager, first["request_id"], step_name="request",
        result=StepResult(status="completed", name="request", step_id="request", output=reply),
    )
    assert submit_human_input(manager.run_root, first["request_id"], reply)["status"] == "consumed"
    assert manager.state is not None
    manager.state.current_step = {"name": "request", "step_id": "request", "visit_count": 2}
    manager.state.step_visits = {"request": 2}
    manager._write_state()
    record_human_input(
        manager, runtime_step_id="request",
        enclosing_step={"step_name": "request", "step_id": "request", "visit_count": 2},
        loop_iteration=None, question="second",
    )
    with pytest.raises(ValueError, match="stale"):
        submit_human_input(manager.run_root, first["request_id"], reply)
