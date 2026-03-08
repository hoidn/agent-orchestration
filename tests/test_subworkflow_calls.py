"""Loader and runtime coverage for reusable workflow imports and call boundaries."""

import json
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


def _managed_write_root_library(*, version: str = "2.5") -> dict:
    return {
        "version": version,
        "name": "write-root-library",
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
        "steps": [
            {
                "name": "WriteOutput",
                "id": "write_output",
                "command": ["bash", "-lc", "printf 'ok\\n'"],
                "output_file": "${inputs.write_root}/result.txt",
            }
        ],
    }


def _run_workflow(
    tmp_path: Path,
    workflow: dict,
    run_id: str,
    *,
    on_error: str = "stop",
) -> tuple[dict, dict]:
    workflow_path = _write_yaml(tmp_path / "workflow.yaml", workflow)
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id=run_id)
    state_manager.initialize("workflow.yaml", context=loaded.get("context", {}))
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    final_state = executor.execute(on_error=on_error)
    persisted = state_manager.load().to_dict()
    return final_state, persisted


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


def test_repeat_until_call_rejects_invariant_write_root_binding(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _managed_write_root_library(version="2.7"),
    )
    caller_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "looped-call-demo",
            "imports": {"review_loop": "workflows/library/review_fix_loop.yaml"},
            "artifacts": {
                "done": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "done": {
                                "kind": "scalar",
                                "type": "bool",
                                "from": {
                                    "ref": "self.steps.MarkDone.artifacts.done",
                                },
                            }
                        },
                        "condition": {
                            "artifact_bool": {
                                "ref": "self.outputs.done",
                            }
                        },
                        "max_iterations": 2,
                        "steps": [
                            {
                                "name": "RunReviewLoop",
                                "id": "run_review_loop",
                                "call": "review_loop",
                                "with": {
                                    "max_cycles": 1,
                                    "write_root": "state/review-loop",
                                },
                            },
                            {
                                "name": "MarkDone",
                                "id": "mark_done",
                                "set_scalar": {
                                    "artifact": "done",
                                    "value": True,
                                },
                            },
                        ],
                    },
                }
            ],
        },
    )

    with pytest.raises(WorkflowValidationError) as exc_info:
        WorkflowLoader(tmp_path).load(caller_path)

    assert any(
        "must vary per invocation" in str(error.message)
        for error in exc_info.value.errors
    )


def test_for_each_call_runtime_rejects_reused_write_root_from_loop_local_ref(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _managed_write_root_library(version="2.5"),
    )
    workflow = {
        "version": "2.5",
        "name": "for-each-call-collision",
        "imports": {"review_loop": "workflows/library/review_fix_loop.yaml"},
        "steps": [
            {
                "name": "ReviewItems",
                "id": "review_items",
                "for_each": {
                    "items": ["a", "b"],
                    "as": "item",
                    "steps": [
                        {
                            "name": "ResolveWriteRoot",
                            "id": "resolve_write_root",
                            "command": ["bash", "-lc", "printf 'state/shared\\n'"],
                            "output_file": "state/shared-write-root.txt",
                            "expected_outputs": [
                                {
                                    "name": "write_root",
                                    "path": "state/shared-write-root.txt",
                                    "type": "relpath",
                                }
                            ],
                        },
                        {
                            "name": "RunReviewLoop",
                            "id": "run_review_loop",
                            "call": "review_loop",
                            "with": {
                                "max_cycles": 1,
                                "write_root": {
                                    "ref": "self.steps.ResolveWriteRoot.artifacts.write_root",
                                },
                            },
                        },
                    ],
                },
            }
        ],
    }

    final_state, persisted = _run_workflow(
        tmp_path,
        workflow,
        run_id="for-each-call-collision-run",
        on_error="continue",
    )

    assert final_state["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["context"]["reason"] == (
        "colliding_write_root_binding"
    )
    assert len(persisted.get("call_frames", {})) == 1


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
    assert frame["state"]["workflow_checksum"].startswith("sha256:")
    assert frame["state"]["workflow_outputs"] == {"approved": True}
    assert frame["state"]["steps"]["SetApproved"]["artifacts"] == {"approved": True}


def test_call_outputs_publish_into_caller_lineage_with_outer_producer(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.5",
            "name": "call-demo",
            "imports": {"review_loop": "workflows/library/review_fix_loop.yaml"},
            "artifacts": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": 3,
                        "write_root": "state/review-loop",
                    },
                    "publishes": [{"artifact": "approved", "from": "approved"}],
                },
                {
                    "name": "ReadApproved",
                    "id": "read_approved",
                    "consumes": [
                        {
                            "artifact": "approved",
                            "producers": ["RunReviewLoop"],
                            "policy": "latest_successful",
                            "freshness": "any",
                        }
                    ],
                    "consume_bundle": {"path": "state/approved_bundle.json"},
                    "command": ["bash", "-lc", "cat state/approved_bundle.json"],
                },
            ],
        },
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-lineage")
    state_manager.initialize("workflow.yaml", context=workflow.get("context", {}))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    state = executor.execute()
    persisted = state_manager.load().to_dict()

    assert state["status"] == "completed"
    assert json.loads(state["steps"]["ReadApproved"]["output"]) == {"approved": True}

    versions = persisted.get("artifact_versions", {}).get("approved", [])
    assert len(versions) == 1
    assert versions[0]["producer"] == "root.run_review_loop"
    assert versions[0]["producer_name"] == "RunReviewLoop"
    assert versions[0]["value"] is True
    assert versions[0]["source_provenance"] == {
        "source_ref": "root.steps.SetApproved.artifacts.approved",
        "source_step_id": "root.set_approved",
        "source_step_name": "SetApproved",
    }

    consumes = persisted.get("artifact_consumes", {}).get("root.read_approved", {})
    assert consumes.get("approved") == 1


def test_call_keeps_callee_context_defaults_isolated_from_caller(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        {
            "version": "2.5",
            "name": "review-fix-loop",
            "context": {
                "decision": "child",
            },
            "steps": [
                {
                    "name": "DoWork",
                    "id": "do_work",
                    "command": ["echo", "ok"],
                }
            ],
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        {
            "version": "2.5",
            "name": "call-context-isolation",
            "context": {
                "decision": "parent",
            },
            "imports": {"review_loop": "workflows/library/review_fix_loop.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                },
                {
                    "name": "ReadParentContext",
                    "id": "read_parent_context",
                    "command": ["bash", "-lc", "printf '%s' '${context.decision}'"],
                },
            ],
        },
        run_id="call-context-isolation",
    )

    assert state["status"] == "completed"
    assert state["steps"]["ReadParentContext"]["output"] == "parent"
    assert persisted["context"] == {"decision": "parent"}

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["state"]["context"] == {"decision": "child"}
    assert frame["bound_inputs"] == {}


def test_call_frame_persists_internal_since_last_consume_bookkeeping(tmp_path: Path):
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
            "artifacts": {
                "failed_count": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [
                {
                    "name": "Initialize",
                    "id": "initialize",
                    "set_scalar": {
                        "artifact": "failed_count",
                        "value": 1,
                    },
                    "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                },
                {
                    "name": "ReadInitial",
                    "id": "read_initial",
                    "consumes": [
                        {
                            "artifact": "failed_count",
                            "producers": ["Initialize"],
                            "policy": "latest_successful",
                            "freshness": "since_last_consume",
                        }
                    ],
                    "consume_bundle": {"path": "${inputs.write_root}/read_initial.json"},
                    "command": ["bash", "-lc", "cat ${inputs.write_root}/read_initial.json"],
                },
                {
                    "name": "Increment",
                    "id": "increment",
                    "increment_scalar": {
                        "artifact": "failed_count",
                        "by": 1,
                    },
                    "publishes": [{"artifact": "failed_count", "from": "failed_count"}],
                },
                {
                    "name": "ReadFresh",
                    "id": "read_fresh",
                    "consumes": [
                        {
                            "artifact": "failed_count",
                            "producers": ["Initialize", "Increment"],
                            "policy": "latest_successful",
                            "freshness": "since_last_consume",
                        }
                    ],
                    "consume_bundle": {"path": "${inputs.write_root}/read_fresh.json"},
                    "command": ["bash", "-lc", "cat ${inputs.write_root}/read_fresh.json"],
                },
            ],
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
                "with": {
                    "write_root": "state/review-loop",
                },
            },
        ),
        run_id="call-freshness",
    )

    assert state["status"] == "completed"
    frame = next(iter(persisted["call_frames"].values()))
    child_state = frame["state"]

    versions = child_state["artifact_versions"]["failed_count"]
    assert [entry["value"] for entry in versions] == [1, 2]
    assert child_state["artifact_consumes"]["root.read_initial"]["failed_count"] == 1
    assert child_state["artifact_consumes"]["root.read_fresh"]["failed_count"] == 2
    assert "root.read_initial" not in persisted.get("artifact_consumes", {})
    assert "root.read_fresh" not in persisted.get("artifact_consumes", {})


def test_call_exports_outputs_after_callee_finalization_completes(tmp_path: Path):
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
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "Cleanup",
                        "id": "cleanup_step",
                        "command": [
                            "bash",
                            "-lc",
                            "mkdir -p state && printf 'cleanup\\n' >> state/call-finalization.log",
                        ],
                    }
                ],
            },
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
        run_id="call-finalization-success",
    )

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["status"] == "completed"
    assert frame["finalization_status"] == "completed"
    assert frame["export_status"] == "completed"
    assert frame["state"]["workflow_outputs"] == {"approved": True}


def test_call_suppresses_outputs_when_callee_finalization_fails(tmp_path: Path):
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
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "FailCleanup",
                        "id": "fail_cleanup",
                        "command": [
                            "bash",
                            "-lc",
                            "mkdir -p state && printf 'cleanup-failed\\n' >> state/call-finalization.log && exit 1",
                        ],
                    }
                ],
            },
        },
    )

    state, persisted = _run_workflow(
        tmp_path,
        _caller_workflow(
            call_step={
                "name": "RunReviewLoop",
                "id": "run_review_loop",
                "call": "review_loop",
            },
        ),
        run_id="call-finalization-failure",
    )

    assert state["status"] == "failed"
    assert state["steps"]["RunReviewLoop"]["status"] == "failed"
    assert state["steps"]["RunReviewLoop"]["error"]["type"] == "call_failed"
    assert "artifacts" not in state["steps"]["RunReviewLoop"]

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["status"] == "failed"
    assert frame["finalization_status"] == "failed"
    assert frame["export_status"] == "suppressed"
    assert frame["state"]["workflow_outputs"] == {}
