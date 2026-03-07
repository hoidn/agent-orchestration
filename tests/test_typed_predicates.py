"""Tests for v1.6 typed predicates, structured refs, and assert routing."""

import json
from pathlib import Path

import pytest
import yaml

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow), encoding="utf-8")
    return workflow_file


def _load_executor(workspace: Path, workflow: dict, run_id: str = "typed-predicate-run") -> WorkflowExecutor:
    workflow_file = _write_workflow(workspace, workflow)
    loader = WorkflowLoader(workspace)
    loaded = loader.load(workflow_file)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    return WorkflowExecutor(loaded, workspace, state_manager)


def test_typed_assert_false_exits_with_assert_failed_and_failure_goto(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "typed-assert-routing",
        "steps": [
                {
                    "name": "WriteReady",
                    "command": ["bash", "-lc", "mkdir -p state && printf 'false' > state/ready.txt"],
                    "expected_outputs": [
                        {"name": "ready", "path": "state/ready.txt", "type": "bool"}
                    ],
                },
            {
                "name": "GateReady",
                "assert": {
                    "artifact_bool": {
                        "ref": "root.steps.WriteReady.artifacts.ready",
                    }
                },
                "on": {"failure": {"goto": "Recovered"}},
            },
            {
                "name": "Recovered",
                "command": ["bash", "-lc", "printf 'recovered' > recovered.txt"],
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow)
    state = executor.execute()

    gate = state["steps"]["GateReady"]
    assert gate["status"] == "failed"
    assert gate["exit_code"] == 3
    assert gate["error"]["type"] == "assert_failed"
    assert gate["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "assert_failed",
        "retryable": False,
    }
    assert state["steps"]["Recovered"]["status"] == "completed"


def test_typed_when_can_branch_on_recovered_failure_outcome(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "typed-when-recovered-failure",
        "steps": [
            {
                "name": "RunCheck",
                "command": ["bash", "-lc", "exit 1"],
                "on": {"failure": {"goto": "GateFailure"}},
            },
            {
                "name": "GateFailure",
                "assert": {
                    "compare": {
                        "left": {"ref": "root.steps.RunCheck.outcome.class"},
                        "op": "eq",
                        "right": "command_failed",
                    }
                },
            },
            {
                "name": "OnlyOnFailure",
                "command": ["bash", "-lc", "printf 'ok' > ok.txt"],
                "when": {
                    "compare": {
                        "left": {"ref": "root.steps.RunCheck.outcome.phase"},
                        "op": "eq",
                        "right": "execution",
                    }
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow, run_id="typed-when-run")
    state = executor.execute(on_error="continue")

    failure = state["steps"]["RunCheck"]
    assert failure["status"] == "failed"
    assert failure["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "command_failed",
        "retryable": False,
    }
    assert state["steps"]["GateFailure"]["status"] == "completed"
    assert state["steps"]["OnlyOnFailure"]["status"] == "completed"


def test_loader_rejects_bare_steps_refs_in_structured_predicates(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "invalid-bare-ref",
        "steps": [{
            "name": "Gate",
            "assert": {
                "compare": {
                    "left": {"ref": "steps.Other.exit_code"},
                    "op": "eq",
                    "right": 0,
                }
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("bare 'steps.'" in str(err.message) for err in exc_info.value.errors)


def test_loader_rejects_self_refs_before_scoped_refs_land(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "invalid-self-ref",
        "steps": [{
            "name": "Gate",
            "assert": {
                "artifact_bool": {
                    "ref": "self.steps.Other.artifacts.ready",
                }
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("self." in str(err.message) for err in exc_info.value.errors)


def test_loader_rejects_refs_to_multi_visit_steps(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "invalid-multi-visit-ref",
        "steps": [
            {
                "name": "Loop",
                "command": ["bash", "-lc", "exit 1"],
                "on": {"failure": {"goto": "Loop"}},
            },
            {
                "name": "Gate",
                "assert": {
                    "compare": {
                        "left": {"ref": "root.steps.Loop.exit_code"},
                        "op": "eq",
                        "right": 1,
                    }
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("multi-visit" in str(err.message) for err in exc_info.value.errors)


def test_loader_rejects_top_level_self_refs_to_multi_visit_steps(tmp_path: Path):
    workflow = {
        "version": "2.0",
        "name": "invalid-top-level-self-multi-visit-ref",
        "steps": [
            {
                "name": "Loop",
                "id": "loop",
                "command": ["bash", "-lc", "exit 1"],
                "on": {"failure": {"goto": "Loop"}},
            },
            {
                "name": "Gate",
                "id": "gate",
                "assert": {
                    "compare": {
                        "left": {"ref": "self.steps.Loop.exit_code"},
                        "op": "eq",
                        "right": 1,
                    }
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("multi-visit" in str(err.message) for err in exc_info.value.errors)


def test_loader_rejects_refs_to_for_each_summary_steps(tmp_path: Path):
    workflow = {
        "version": "2.0",
        "name": "invalid-for-each-summary-ref",
        "steps": [
            {
                "name": "Loop",
                "id": "loop",
                "for_each": {
                    "items": ["one"],
                    "steps": [
                        {
                            "name": "StepA",
                            "id": "step_a",
                            "command": ["bash", "-lc", "printf '%s' \"${item}\""],
                        }
                    ],
                },
            },
            {
                "name": "Gate",
                "id": "gate",
                "assert": {
                    "compare": {
                        "left": {"ref": "self.steps.Loop.exit_code"},
                        "op": "eq",
                        "right": 0,
                    }
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("for_each" in str(err.message) for err in exc_info.value.errors)


def test_loader_rejects_missing_root_step_exit_code_refs(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "predicate-missing-step",
        "steps": [{
            "name": "Gate",
            "assert": {
                "compare": {
                    "left": {"ref": "root.steps.Missing.exit_code"},
                    "op": "eq",
                    "right": 0,
                }
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("targets unknown step" in str(err.message) for err in exc_info.value.errors)


def test_loader_rejects_unknown_outcome_members(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "predicate-invalid-outcome-field",
        "steps": [
            {
                "name": "First",
                "command": ["bash", "-lc", "exit 0"],
            },
            {
                "name": "Gate",
                "assert": {
                    "compare": {
                        "left": {"ref": "root.steps.First.outcome.not_a_field"},
                        "op": "eq",
                        "right": "execution",
                    }
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)

    with pytest.raises(WorkflowValidationError) as exc_info:
        loader.load(workflow_file)

    assert any("invalid outcome field" in str(err.message) for err in exc_info.value.errors)


def test_runtime_predicate_missing_self_scope_value_fails_with_structured_error(tmp_path: Path):
    workflow = {
        "version": "2.0",
        "name": "predicate-missing-self-value",
        "artifacts": {
            "ready": {
                "kind": "scalar",
                "type": "bool",
            },
        },
        "steps": [{
            "name": "Loop",
            "id": "loop",
            "for_each": {
                "items": ["one"],
                "steps": [
                    {
                        "name": "Gate",
                        "id": "gate",
                        "assert": {
                            "compare": {
                                "left": {"ref": "self.steps.Future.exit_code"},
                                "op": "eq",
                                "right": 0,
                            }
                        },
                    },
                    {
                        "name": "Future",
                        "id": "future",
                        "set_scalar": {
                            "artifact": "ready",
                            "value": True,
                        },
                    },
                ],
            },
        }],
    }

    executor = _load_executor(tmp_path, workflow, run_id="predicate-missing-self")
    state = executor.execute(on_error="continue")

    gate = state["steps"]["Loop[0].Gate"]
    assert gate["status"] == "failed"
    assert gate["exit_code"] == 2
    assert gate["error"]["type"] == "predicate_evaluation_failed"
    assert gate["outcome"] == {
        "status": "failed",
        "phase": "pre_execution",
        "class": "pre_execution_failed",
        "retryable": False,
    }


def test_v2_structured_refs_can_target_step_names_containing_dots(tmp_path: Path):
    workflow = {
        "version": "2.0",
        "name": "dotted-step-name-ref",
        "steps": [
            {
                "name": "Build.v1",
                "id": "build_v1",
                "command": ["bash", "-lc", "mkdir -p state && printf 'true' > state/ready.txt"],
                "expected_outputs": [
                    {
                        "name": "ready",
                        "path": "state/ready.txt",
                        "type": "bool",
                    }
                ],
            },
            {
                "name": "Gate",
                "id": "gate",
                "assert": {
                    "artifact_bool": {
                        "ref": "root.steps.Build.v1.artifacts.ready",
                    }
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow, run_id="dotted-step-name-ref")
    state = executor.execute()

    assert state["steps"]["Build.v1"]["status"] == "completed"
    assert state["steps"]["Gate"]["status"] == "completed"
