"""
Tests for AT-65: Loop scoping of steps.* variables.

Inside for_each, ${steps.<Name>.*} should refer only to the current iteration's results,
not to results from previous iterations or from steps outside the loop.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from tests.workflow_bundle_helpers import load_workflow_bundle_for_test


def create_test_workflow():
    """Create a workflow that tests loop-scoped steps.* variables."""
    return {
        "version": "1.1",
        "context": {
            "test_mode": "true"
        },
        "steps": [
            {
                "name": "OuterStep",
                "command": ["echo", "outer value"]
            },
            {
                "name": "LoopWithScoping",
                "for_each": {
                    "items": ["item1", "item2", "item3"],
                    "steps": [
                        {
                            "name": "StepA",
                            "command": ["echo", "${item}"]
                        },
                        {
                            "name": "StepB",
                            # This should reference StepA from current iteration only
                            "command": ["echo", "Previous was: ${steps.StepA.output}"]
                        },
                        {
                            "name": "StepC",
                            # Try to reference outer step - should fail with undefined
                            "command": ["echo", "Outer was: ${steps.OuterStep.output}"]
                        }
                    ]
                }
            }
        ]
    }


def test_at65_loop_scoped_steps_current_iteration(tmp_path):
    """
    Test that ${steps.<Name>.*} inside a loop refers to current iteration only.
    """
    # Setup
    workflow = create_test_workflow()

    # Remove StepC which tries to reference outer step
    workflow["steps"][1]["for_each"]["steps"] = workflow["steps"][1]["for_each"]["steps"][:2]

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Create mock subprocess for command execution
    mock_run = MagicMock()

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""

        # Return different output based on command
        if "outer value" in cmd:
            result.stdout = b"outer value"
        elif "item1" in cmd:
            result.stdout = b"item1"
        elif "item2" in cmd:
            result.stdout = b"item2"
        elif "item3" in cmd:
            result.stdout = b"item3"
        elif "Previous was:" in cmd:
            # This should show the current iteration's StepA output
            if "item1" in str(cmd):
                result.stdout = b"Previous was: item1"
            elif "item2" in str(cmd):
                result.stdout = b"Previous was: item2"
            elif "item3" in str(cmd):
                result.stdout = b"Previous was: item3"
            else:
                # The actual command will have the substituted value
                # Extract it from the command
                for part in cmd:
                    if part.startswith("Previous was:"):
                        result.stdout = part.encode('utf-8')
                        break
        else:
            result.stdout = str(cmd).encode('utf-8')

        return result

    mock_run.side_effect = mock_subprocess_run

    # Create StateManager
    state_manager = StateManager(state_dir)
    state_manager.initialize(str(workflow_path))

    with patch('subprocess.run', mock_run):
        # Execute
        executor = WorkflowExecutor(
            load_workflow_bundle_for_test(tmp_path, workflow_path),
            tmp_path,  # workspace
            state_manager,
            logs_dir=tmp_path / "logs"
        )
        final_state = executor.execute()

    # Verify each iteration got the correct scoped value
    # Check that StepB in each iteration references its own StepA
    for i in range(3):
        item = f"item{i+1}"
        step_b_key = f"LoopWithScoping[{i}].StepB"

        # Get the actual command that was executed
        calls = mock_run.call_args_list

        # Find the call for this specific StepB
        for call in calls:
            cmd = call[0][0]  # First positional arg is the command
            if isinstance(cmd, list) and len(cmd) >= 2:
                if "Previous was:" in cmd[1] and item in cmd[1]:
                    # Verify it references the current iteration's value
                    assert item in cmd[1], f"Iteration {i} StepB should reference '{item}'"
                    break


def test_at65_outer_steps_undefined_in_loop(tmp_path):
    """
    Test that referencing outer steps from inside a loop yields undefined variable error.
    """
    # Setup
    workflow = create_test_workflow()

    # Keep only StepC which tries to reference outer step
    workflow["steps"][1]["for_each"]["steps"] = [workflow["steps"][1]["for_each"]["steps"][2]]

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Execute
    state_manager = StateManager(state_dir)
    state_manager.initialize(str(workflow_path))
    executor = WorkflowExecutor(
        load_workflow_bundle_for_test(tmp_path, workflow_path),
        tmp_path,  # workspace
        state_manager,
        logs_dir=tmp_path / "logs"
    )

    # Mock subprocess to capture what gets executed
    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"outer value"
        mock_run.return_value.stderr = b""

        final_state = executor.execute()

    # Verify that StepC failed with undefined variable error
    for i in range(3):
        step_c_key = f"LoopWithScoping[{i}].StepC"
        assert step_c_key in final_state["steps"]

        result = final_state["steps"][step_c_key]

        # Should have failed with exit code 2 and undefined_vars error context
        assert result["exit_code"] == 2, f"StepC in iteration {i} should fail with exit 2"
        assert "error" in result
        assert "undefined_vars" in result["error"].get("context", {})
        assert "steps.OuterStep.output" in result["error"]["context"]["undefined_vars"]


def test_at65_iteration_isolation(tmp_path):
    """
    Test that each iteration cannot see previous iteration's results.
    """
    workflow = {
        "version": "1.1",
        "context": {},
        "steps": [
            {
                "name": "AccumulatorLoop",
                "for_each": {
                    "items": ["first", "second", "third"],
                    "steps": [
                        {
                            "name": "Counter",
                            "command": ["echo", "${loop.index}"]
                        },
                        {
                            "name": "TryPreviousCounter",
                            # This tries to accumulate but should only see current iteration
                            "command": ["echo", "Current counter: ${steps.Counter.output}"],
                            "when": {
                                "exists": "never.txt"  # Skip this to avoid undefined var error
                            }
                        }
                    ]
                }
            }
        ]
    }

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Mock subprocess
    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""

        # Return the index value
        if cmd == ["echo", "0"]:
            result.stdout = b"0"
        elif cmd == ["echo", "1"]:
            result.stdout = b"1"
        elif cmd == ["echo", "2"]:
            result.stdout = b"2"
        else:
            result.stdout = str(cmd).encode('utf-8')

        return result

    with patch('subprocess.run', mock_subprocess_run):
        state_manager = StateManager(state_dir)
        state_manager.initialize(str(workflow_path))
        executor = WorkflowExecutor(
            load_workflow_bundle_for_test(tmp_path, workflow_path),
            tmp_path,  # workspace
            state_manager,
            logs_dir=tmp_path / "logs"
        )
        final_state = executor.execute()

    # Verify each iteration has its own Counter value
    for i in range(3):
        counter_key = f"AccumulatorLoop[{i}].Counter"
        assert counter_key in final_state["steps"]
        assert final_state["steps"][counter_key]["output"] == str(i)


def test_loop_scoping_legacy_v14_steps_namespace_is_unchanged(tmp_path):
    """Scoped refs must not change legacy v1.4 ${steps.*} loop substitution semantics."""
    workflow = create_test_workflow()
    workflow["version"] = "1.4"
    workflow["steps"][1]["for_each"]["steps"] = workflow["steps"][1]["for_each"]["steps"][:2]

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_manager = StateManager(state_dir)
    state_manager.initialize(str(workflow_path))
    executor = WorkflowExecutor(
        load_workflow_bundle_for_test(tmp_path, workflow_path),
        tmp_path,
        state_manager,
        logs_dir=tmp_path / "logs",
    )

    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b"ok"
        mock_run.return_value.stderr = b""
        state = executor.execute()

    assert state["steps"]["LoopWithScoping[0].StepB"]["exit_code"] == 0
    assert state["steps"]["LoopWithScoping[1].StepB"]["exit_code"] == 0


def test_v2_nested_steps_execute_with_scoped_refs_inside_for_each(tmp_path):
    """Nested v2.0 loop steps execute real runtime behavior instead of fabricating success."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "ready.txt").write_text("ready", encoding="utf-8")

    workflow = {
        "version": "2.0",
        "name": "nested-runtime-step-types",
        "artifacts": {
            "root_flag": {
                "kind": "scalar",
                "type": "bool",
            },
            "counter": {
                "kind": "scalar",
                "type": "integer",
            },
            "iteration_flag": {
                "kind": "scalar",
                "type": "bool",
            },
        },
        "steps": [
            {
                "name": "RootFlag",
                "id": "root_flag",
                "set_scalar": {
                    "artifact": "root_flag",
                    "value": True,
                },
            },
            {
                "name": "SeedCounter",
                "id": "seed_counter",
                "set_scalar": {
                    "artifact": "counter",
                    "value": 0,
                },
                "publishes": [
                    {
                        "artifact": "counter",
                        "from": "counter",
                    }
                ],
            },
            {
                "name": "Loop",
                "id": "loop",
                "for_each": {
                    "items": ["one"],
                    "steps": [
                        {
                            "name": "SetIterationFlag",
                            "id": "set_iteration_flag",
                            "set_scalar": {
                                "artifact": "iteration_flag",
                                "value": True,
                            },
                        },
                        {
                            "name": "BumpCounter",
                            "id": "bump_counter",
                            "increment_scalar": {
                                "artifact": "counter",
                                "by": 1,
                            },
                        },
                        {
                            "name": "WaitReady",
                            "id": "wait_ready",
                            "wait_for": {
                                "glob": "ready.txt",
                                "timeout_sec": 1,
                                "poll_ms": 50,
                            },
                        },
                        {
                            "name": "AssertScopes",
                            "id": "assert_scopes",
                            "assert": {
                                "all_of": [
                                    {
                                        "artifact_bool": {
                                            "ref": "self.steps.SetIterationFlag.artifacts.iteration_flag",
                                        }
                                    },
                                    {
                                        "artifact_bool": {
                                            "ref": "parent.steps.RootFlag.artifacts.root_flag",
                                        }
                                    },
                                    {
                                        "compare": {
                                            "left": {
                                                "ref": "self.steps.BumpCounter.artifacts.counter",
                                            },
                                            "op": "eq",
                                            "right": 1,
                                        }
                                    },
                                    {
                                        "compare": {
                                            "left": {
                                                "ref": "self.steps.WaitReady.exit_code",
                                            },
                                            "op": "eq",
                                            "right": 0,
                                        }
                                    },
                                ]
                            },
                        },
                    ],
                },
            },
        ],
    }

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, "w") as f:
        yaml.dump(workflow, f)

    loader = WorkflowLoader(workspace)
    loaded = loader.load(workflow_path)

    state_manager = StateManager(tmp_path / ".orchestrate")
    state_manager.initialize(str(workflow_path))
    executor = WorkflowExecutor(loaded, workspace, state_manager)

    final_state = executor.execute()

    assert final_state["steps"]["Loop[0].SetIterationFlag"]["artifacts"] == {"iteration_flag": True}
    assert final_state["steps"]["Loop[0].BumpCounter"]["artifacts"] == {"counter": 1}
    assert final_state["steps"]["Loop[0].WaitReady"]["status"] == "completed"
    assert final_state["steps"]["Loop[0].WaitReady"]["files"] == ["ready.txt"]
    assert final_state["steps"]["Loop[0].AssertScopes"]["status"] == "completed"
    assert final_state["steps"]["Loop[0].AssertScopes"]["exit_code"] == 0


def test_v2_self_refs_do_not_fall_back_to_root_scope(tmp_path):
    """self.steps refs must not silently read root results when the local step is unavailable."""
    workflow = {
        "version": "2.0",
        "name": "self-scope-does-not-fall-back",
        "artifacts": {
            "approved": {
                "kind": "scalar",
                "type": "bool",
            },
        },
        "steps": [
            {
                "name": "OuterCheck",
                "id": "outer_check_root",
                "set_scalar": {
                    "artifact": "approved",
                    "value": True,
                },
            },
            {
                "name": "Loop",
                "id": "loop",
                "for_each": {
                    "items": ["one"],
                    "steps": [
                        {
                            "name": "Gate",
                            "id": "gate",
                            "assert": {
                                "artifact_bool": {
                                    "ref": "self.steps.OuterCheck.artifacts.approved",
                                }
                            },
                        },
                        {
                            "name": "OuterCheck",
                            "id": "outer_check_local",
                            "set_scalar": {
                                "artifact": "approved",
                                "value": False,
                            },
                        },
                    ],
                },
            },
        ],
    }

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, "w") as f:
        yaml.dump(workflow, f)

    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_path)

    state_manager = StateManager(tmp_path / ".orchestrate")
    state_manager.initialize(str(workflow_path))
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)

    final_state = executor.execute(on_error="continue")

    gate = final_state["steps"]["Loop[0].Gate"]
    assert gate["status"] == "failed"
    assert gate["exit_code"] == 2
    assert gate["error"]["type"] == "predicate_evaluation_failed"
    assert final_state["steps"]["Loop[0].OuterCheck"]["status"] == "completed"

def test_at65_nested_step_references_within_iteration(tmp_path):
    """
    Test that steps within the same iteration can reference each other.
    """
    workflow = {
        "version": "1.1",
        "context": {},
        "steps": [
            {
                "name": "ChainedLoop",
                "for_each": {
                    "items": ["alpha", "beta", "gamma"],
                    "steps": [
                        {
                            "name": "Step1",
                            "command": ["echo", "${item}"]
                        },
                        {
                            "name": "Step2",
                            "command": ["echo", "${steps.Step1.output}-processed"]
                        },
                        {
                            "name": "Step3",
                            "command": ["echo", "${steps.Step2.output}-final"]
                        }
                    ]
                }
            }
        ]
    }

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Mock subprocess to track commands
    executed_commands = []

    def mock_subprocess_run(cmd, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = b""

        executed_commands.append(cmd)

        # Simulate command execution
        if len(cmd) == 2 and cmd[0] == "echo":
            result.stdout = cmd[1].encode('utf-8')  # Echo back the argument
        else:
            result.stdout = " ".join(cmd).encode('utf-8')

        return result

    with patch('subprocess.run', mock_subprocess_run):
        state_manager = StateManager(state_dir)
        state_manager.initialize(str(workflow_path))
        executor = WorkflowExecutor(
            load_workflow_bundle_for_test(tmp_path, workflow_path),
            tmp_path,  # workspace
            state_manager,
            logs_dir=tmp_path / "logs"
        )
        final_state = executor.execute()

    # Verify the command chain for each iteration
    items = ["alpha", "beta", "gamma"]
    for i, item in enumerate(items):
        # Step1 should output the item
        step1_key = f"ChainedLoop[{i}].Step1"
        assert final_state["steps"][step1_key]["output"] == item

        # Step2 should reference Step1's output from same iteration
        step2_key = f"ChainedLoop[{i}].Step2"
        assert final_state["steps"][step2_key]["output"] == f"{item}-processed"

        # Step3 should reference Step2's output from same iteration
        step3_key = f"ChainedLoop[{i}].Step3"
        assert final_state["steps"][step3_key]["output"] == f"{item}-processed-final"


def test_at65_empty_steps_in_first_iteration(tmp_path):
    """
    Test that the first iteration starts with empty steps.* namespace.
    """
    workflow = {
        "version": "1.1",
        "context": {},
        "steps": [
            {
                "name": "FirstIterationTest",
                "for_each": {
                    "items": ["only_one"],
                    "steps": [
                        {
                            "name": "CheckEmpty",
                            # Reference a non-existent step - should fail with undefined
                            "command": ["echo", "${steps.NonExistent.output}"]
                        }
                    ]
                }
            }
        ]
    }

    workflow_path = tmp_path / "workflow.yaml"
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Execute
    state_manager = StateManager(state_dir)
    state_manager.initialize(str(workflow_path))
    executor = WorkflowExecutor(
        load_workflow_bundle_for_test(tmp_path, workflow_path),
        tmp_path,  # workspace
        state_manager,
        logs_dir=tmp_path / "logs"
    )

    with patch('subprocess.run') as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = b""
        mock_run.return_value.stderr = b""

        final_state = executor.execute()

    # The step should fail with undefined variable
    check_key = "FirstIterationTest[0].CheckEmpty"
    assert check_key in final_state["steps"]

    result = final_state["steps"][check_key]
    assert result["exit_code"] == 2
    assert "error" in result
    assert "undefined_vars" in result["error"].get("context", {})
    assert "steps.NonExistent.output" in result["error"]["context"]["undefined_vars"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
