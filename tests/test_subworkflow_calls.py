"""Loader and runtime coverage for reusable workflow imports and call boundaries."""

import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.surface_ast import freeze_mapping
from tests.workflow_bundle_helpers import (
    bundle_context_dict,
    materialize_projection_body_steps,
    thaw_surface_workflow,
)


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
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(loaded))
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


def test_call_executes_from_loaded_bundle_without_legacy_import_magic(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
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

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    state_manager = StateManager(tmp_path, run_id="bundle-call")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    final_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()

    assert final_state["status"] == "completed"
    assert final_state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}


def test_call_uses_typed_import_contracts_when_legacy_specs_are_missing(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
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

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    state_manager = StateManager(tmp_path, run_id="bundle-call-typed-contracts")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    final_state = WorkflowExecutor(bundle, tmp_path, state_manager).execute()
    persisted = state_manager.load().to_dict()

    assert final_state["status"] == "completed"
    assert final_state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}

    frame = next(iter(persisted["call_frames"].values()))
    assert frame["bound_inputs"] == {
        "max_cycles": 3,
        "write_root": "state/review-loop",
    }
    assert frame["export_status"] == "completed"
    assert frame["state"]["workflow_outputs"] == {"approved": True}


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


def test_call_rejects_colliding_write_root_bindings_without_imported_legacy_magic(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _managed_write_root_library(version="2.7"),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "for-each-call-collision-typed-imports",
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
                },
            ],
        },
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)

    state_manager = StateManager(tmp_path, run_id="for-each-call-collision-typed-imports")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(on_error="continue")
    persisted = state_manager.load().to_dict()

    assert state["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert state["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["context"]["reason"] == (
        "colliding_write_root_binding"
    )
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["type"] == "contract_violation"
    assert persisted["steps"]["ReviewItems[1].RunReviewLoop"]["error"]["context"]["reason"] == (
        "colliding_write_root_binding"
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
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
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
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
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


def test_call_repeat_until_provider_defaults_use_callee_context(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_loop.yaml",
        {
            "version": "2.7",
            "name": "review-loop",
            "context": {
                "workflow_model": "gpt-5.4",
                "workflow_effort": "high",
            },
            "inputs": {
                "state_root": {
                    "kind": "relpath",
                    "type": "relpath",
                }
            },
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                    "from": {
                        "ref": "root.steps.ReviewLoop.artifacts.review_decision",
                    },
                }
            },
            "providers": {
                "reviewer": {
                    "command": [
                        "fake-reviewer",
                        "--model",
                        "${model}",
                        "--effort",
                        "${effort}",
                    ],
                    "input_mode": "stdin",
                    "defaults": {
                        "model": "${context.workflow_model}",
                        "effort": "${context.workflow_effort}",
                    },
                }
            },
            "steps": [
                {
                    "name": "Initialize",
                    "id": "initialize",
                    "command": [
                        "bash",
                        "-lc",
                        "mkdir -p \"${inputs.state_root}\"",
                    ],
                },
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "review_iteration",
                        "max_iterations": 2,
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.Review.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {
                                    "ref": "self.outputs.review_decision",
                                },
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "steps": [
                            {
                                "name": "Review",
                                "id": "review",
                                "provider": "reviewer",
                                "expected_outputs": [
                                    {
                                        "name": "review_decision",
                                        "path": "${inputs.state_root}/decision.txt",
                                        "type": "enum",
                                        "allowed": ["APPROVE", "REVISE"],
                                    }
                                ],
                            }
                        ],
                    },
                },
            ],
        },
    )

    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "call-repeat-until-provider-context",
            "imports": {"review_loop": "workflows/library/review_loop.yaml"},
            "steps": [
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "state_root": "state/review-loop",
                    },
                }
            ],
        },
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(tmp_path, run_id="call-repeat-until-provider-context")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(workflow))
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    captured_commands: list[list[str]] = []

    def _execute(_self, invocation, **_kwargs):
        captured_commands.append(list(invocation.command))
        decision_path = tmp_path / "state" / "review-loop" / "decision.txt"
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        decision_path.write_text("APPROVE\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    with patch.object(ProviderExecutor, "execute", _execute):
        state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"review_decision": "APPROVE"}
    assert captured_commands == [["fake-reviewer", "--model", "gpt-5.4", "--effort", "high"]]


def test_call_uses_bound_inputs_when_legacy_ref_is_corrupted(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(version="2.7"),
    )
    workflow_path = _write_yaml(
        tmp_path / "workflow.yaml",
        {
            "version": "2.7",
            "name": "bound-call-inputs",
            "imports": {"review_loop": "workflows/library/review_fix_loop.yaml"},
            "artifacts": {
                "max_cycles": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [
                {
                    "name": "WriteMaxCycles",
                    "id": "write_max_cycles",
                    "set_scalar": {
                        "artifact": "max_cycles",
                        "value": 3,
                    },
                },
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "call": "review_loop",
                    "with": {
                        "max_cycles": {"ref": "root.steps.WriteMaxCycles.artifacts.max_cycles"},
                        "write_root": "state/review-loop",
                    },
                },
            ],
        },
    )

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    call_node = bundle.ir.nodes["root.run_review_loop"]
    corrupted_raw = {
        **dict(call_node.raw),
        "with": {
            **dict(call_node.raw.get("with", {})),
            "max_cycles": {"ref": "root.steps.Missing.artifacts.max_cycles"},
        },
    }
    bundle = replace(
        bundle,
        ir=replace(
            bundle.ir,
            nodes=MappingProxyType({
                **bundle.ir.nodes,
                "root.run_review_loop": replace(
                    call_node,
                    raw=freeze_mapping(corrupted_raw),
                ),
            }),
        ),
    )
    state_manager = StateManager(tmp_path, run_id="bound-call-inputs")
    state_manager.initialize("workflow.yaml")
    state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["steps"]["RunReviewLoop"]["artifacts"] == {"approved": True}


def test_call_debug_exports_use_bound_output_addresses_when_surface_ref_is_corrupted(tmp_path: Path):
    _write_yaml(
        tmp_path / "workflows" / "library" / "review_fix_loop.yaml",
        _library_workflow(),
    )
    workflow_path = _write_yaml(
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

    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    imported_bundle = bundle.imports["review_loop"]
    assert not hasattr(imported_bundle.surface.outputs["approved"], "raw")

    corrupted_surface_raw = thaw_surface_workflow(imported_bundle)
    corrupted_surface_raw["outputs"]["approved"]["from"]["ref"] = (
        "root.steps.Missing.artifacts.approved"
    )
    corrupted_surface = replace(
        imported_bundle.surface,
        raw=freeze_mapping(corrupted_surface_raw),
    )
    corrupted_bundle = replace(imported_bundle, surface=corrupted_surface)

    state_manager = StateManager(tmp_path, run_id="bound-call-output-provenance")
    state_manager.initialize("workflow.yaml", context=bundle_context_dict(bundle))
    executor = WorkflowExecutor(bundle, tmp_path, state_manager)
    state = executor.execute()
    persisted = state_manager.load().to_dict()
    frame_id, frame = next(iter(persisted["call_frames"].items()))

    debug_payload = executor.call_executor.build_debug_payload(
        frame_id=frame_id,
        step=materialize_projection_body_steps(bundle)[0],
        imported_workflow=corrupted_bundle,
        child_state=frame["state"],
    )

    assert state["status"] == "completed"
    assert debug_payload["exports"]["approved"] == {
        "source_ref": "root.steps.SetApproved.artifacts.approved",
        "source_step_id": "root.set_approved",
        "source_step_name": "SetApproved",
    }


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
