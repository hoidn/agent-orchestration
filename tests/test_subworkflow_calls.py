"""Loader and runtime coverage for reusable workflow imports and call boundaries."""

from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _library_workflow(*, version: str = "2.5") -> dict:
    return {
        "version": version,
        "name": "review-fix-loop",
        "inputs": {
            "max_cycles": {
                "kind": "scalar",
                "type": "integer",
            },
            "write_root": {
                "kind": "relpath",
                "type": "relpath",
            },
        },
        "outputs": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
                "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
            }
        },
        "artifacts": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
            }
        },
        "steps": [
            {
                "name": "SetApproved",
                "id": "set_approved",
                "set_scalar": {
                    "artifact": "approved",
                    "value": True,
                },
            }
        ],
    }


def _caller_workflow(*, call_step: dict, imports: dict | None = None, version: str = "2.5") -> dict:
    return {
        "version": version,
        "name": "call-demo",
        "imports": imports or {"review_loop": "workflows/library/review_fix_loop.yaml"},
        "steps": [call_step],
    }


def test_imported_workflows_must_validate_independently(tmp_path: Path):
    library_path = _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        {
            "version": "2.5",
            "name": "invalid-library",
            "providers": {
                "broken": {
                    "input_mode": "stdin",
                }
            },
            "steps": [
                {
                    "name": "Review",
                    "provider": "broken",
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
            imports={"review_loop": str(library_path.relative_to(tmp_path))},
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    messages = [str(error.message) for error in exc_info.value.errors]
    assert any("Import 'review_loop'" in message for message in messages)
    assert any("missing required 'command' field" in message for message in messages)


def test_call_requires_authored_stable_id(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "call requires an authored stable 'id'" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_mixed_caller_callee_versions(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(version="2.4"),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "must declare the same DSL version" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_with_literal_binding_must_match_callee_input_type(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "max_cycles": "not-an-int",
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "call.with.max_cycles is invalid" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_unknown_import_alias(tmp_path: Path):
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "missing_loop",
                "with": {
                    "max_cycles": 3,
                    "write_root": "state/review-loop",
                },
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "unknown import alias 'missing_loop'" in str(error.message)
        for error in exc_info.value.errors
    )


def test_import_path_rejects_source_tree_escape(tmp_path: Path):
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
            imports={"review_loop": "../outside.yaml"},
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "workflow source tree" in str(error.message)
        for error in exc_info.value.errors
    )


def test_reusable_workflow_rejects_hard_coded_dsl_managed_write_root(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "steps": [
                {
                    "name": "WriteOutput",
                    "id": "write_output",
                    "command": ["bash", "-lc", "printf 'ok\\n'"],
                    "output_file": "state/fixed-output.txt",
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "DSL-managed write roots" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_rejects_colliding_write_root_bindings(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "inputs": {
                "write_root": {
                    "kind": "relpath",
                    "type": "relpath",
                }
            },
            "steps": [
                {
                    "name": "WriteOutput",
                    "id": "write_output",
                    "command": ["bash", "-lc", "printf 'ok\\n'"],
                    "output_file": "${inputs.write_root}/result.txt",
                }
            ],
        },
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "call-demo",
            "imports": {"review_loop": "workflows/library/review_fix_loop.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoopA",
                    "id": "run_review_loop_a",
                    "call": "review_loop",
                    "with": {
                        "write_root": "state/shared",
                    },
                },
                {
                    "name": "RunReviewLoopB",
                    "id": "run_review_loop_b",
                    "call": "review_loop",
                    "with": {
                        "write_root": "state/shared",
                    },
                },
            ],
        },
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "colliding write-root bindings" in str(error.message)
        for error in exc_info.value.errors
    )


def test_call_executes_imported_workflow_and_persists_call_frame_state(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.SetApproved.artifacts.approved"},
                }
            },
            "steps": [
                {
                    "name": "SetApproved",
                    "id": "set_approved",
                    "set_scalar": {
                        "artifact": "approved",
                        "value": True,
                    },
                }
            ],
        },
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-run")
    state_manager.initialize("workflow.yaml", context=workflow.get("context", {}))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}
    assert "SetApproved" not in state["steps"]

    call_frames = state.get("call_frames", {})
    assert len(call_frames) == 1
    frame = next(iter(call_frames.values()))
    assert frame["import_alias"] == "review_loop"
    assert frame["status"] == "completed"
    assert frame["export_status"] == "completed"
    assert frame["state"]["workflow_outputs"] == {"approved": True}
    assert frame["state"]["steps"]["SetApproved"]["artifacts"] == {"approved": True}
