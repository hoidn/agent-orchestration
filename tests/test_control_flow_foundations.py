"""Tests for cycle-guard control-flow foundations (Task 5 / D3)."""

from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow), encoding="utf-8")
    return workflow_file


def _load_executor(workspace: Path, workflow: dict, run_id: str) -> WorkflowExecutor:
    workflow_file = _write_workflow(workspace, workflow)
    loader = WorkflowLoader(workspace)
    loaded = loader.load(workflow_file)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("workflow.yaml")
    return WorkflowExecutor(loaded, workspace, state_manager)


def test_skipped_steps_do_not_consume_visit_budget(tmp_path: Path):
    workflow = {
        "version": "1.8",
        "name": "skip-does-not-visit",
        "max_transitions": 8,
        "steps": [
            {
                "name": "LoopStart",
                "max_visits": 2,
                "command": ["bash", "-lc", "printf 'loop'"],
            },
            {
                "name": "MaybeSkip",
                "max_visits": 1,
                "command": ["bash", "-lc", "printf 'should-not-run'"],
                "when": {
                    "equals": {
                        "left": "skip",
                        "right": "run",
                    }
                },
            },
            {
                "name": "LoopBack",
                "command": ["bash", "-lc", "printf 'back'"],
                "on": {
                    "success": {
                        "goto": "LoopStart",
                    }
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow, run_id="skip-visits-run")
    state = executor.execute(on_error="continue")

    assert state["status"] == "failed"
    assert state["steps"]["LoopStart"]["error"]["type"] == "cycle_guard_exceeded"
    assert state["steps"]["MaybeSkip"]["status"] == "skipped"
    assert state["step_visits"]["LoopStart"] == 3
    assert state["step_visits"].get("MaybeSkip", 0) == 0


def test_back_edge_loops_consume_transition_budget_and_fail_pre_execution(tmp_path: Path):
    workflow = {
        "version": "1.8",
        "name": "transition-guard-loop",
        "artifacts": {
            "loop_budget": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "max_transitions": 4,
        "steps": [
            {
                "name": "InitializeBudget",
                "set_scalar": {
                    "artifact": "loop_budget",
                    "value": 1,
                },
            },
            {
                "name": "RunCheck",
                "command": ["bash", "-lc", "exit 1"],
                "on": {
                    "failure": {
                        "goto": "GuardLoop",
                    }
                },
            },
            {
                "name": "GuardLoop",
                "assert": {
                    "compare": {
                        "left": {"ref": "root.steps.InitializeBudget.artifacts.loop_budget"},
                        "op": "eq",
                        "right": 1,
                    }
                },
                "on": {
                    "success": {
                        "goto": "RunCheck",
                    }
                },
            },
        ],
    }

    executor = _load_executor(tmp_path, workflow, run_id="transition-guard-run")
    state = executor.execute(on_error="continue")

    assert state["status"] == "failed"
    assert state["transition_count"] == 6
    assert state["steps"]["GuardLoop"]["error"]["type"] == "cycle_guard_exceeded"
    assert state["steps"]["GuardLoop"]["outcome"] == {
        "status": "failed",
        "phase": "pre_execution",
        "class": "pre_execution_failed",
        "retryable": False,
    }
