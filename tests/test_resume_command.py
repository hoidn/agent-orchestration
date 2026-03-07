"""Tests for the CLI resume command (AT-4)."""

import json
import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import hashlib
import yaml

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader


def _build_resume_loop_workflow() -> dict:
    return {
        "version": "1.1",
        "name": "Resume Loop Workflow",
        "steps": [
            {
                "name": "ReviewImplementation",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=$(cat state/review_count.txt 2>/dev/null || printf '0')",
                            "count=$((count + 1))",
                            "printf '%s\\n' \"$count\" > state/review_count.txt",
                            "if [ \"$count\" -ge 2 ]; then",
                            "  printf 'APPROVE\\n' > state/decision.txt",
                            "else",
                            "  printf 'REVISE\\n' > state/decision.txt",
                            "fi",
                            "printf 'review-%s\\n' \"$count\" >> state/history.log",
                        ]
                    ),
                ],
            },
            {
                "name": "ImplementationReviewGate",
                "command": ["bash", "-lc", "test \"$(cat state/decision.txt)\" = APPROVE"],
                "on": {"success": {"goto": "_end"}, "failure": {"goto": "ImplementationCycleGate"}},
            },
            {
                "name": "ImplementationCycleGate",
                "command": ["bash", "-lc", "test \"$(cat state/cycle.txt)\" -lt 20"],
                "on": {"success": {"goto": "FixImplementation"}, "failure": {"goto": "MaxImplementationCyclesExceeded"}},
            },
            {
                "name": "FixImplementation",
                "command": ["bash", "-lc", "printf 'fix\\n' >> state/history.log"],
                "on": {"success": {"goto": "IncrementImplementationCycle"}},
            },
            {
                "name": "IncrementImplementationCycle",
                "command": [
                    "bash",
                    "-lc",
                    "\n".join(
                        [
                            "count=$(cat state/cycle.txt 2>/dev/null || printf '0')",
                            "count=$((count + 1))",
                            "printf '%s\\n' \"$count\" > state/cycle.txt",
                            "printf 'increment-%s\\n' \"$count\" >> state/history.log",
                        ]
                    ),
                ],
                "on": {"success": {"goto": "ReviewImplementation"}},
            },
            {
                "name": "MaxImplementationCyclesExceeded",
                "command": ["bash", "-lc", "printf 'maxed\\n' >> state/history.log && exit 1"],
            },
        ],
    }


def _seed_resume_loop_state(workspace: Path, *, run_id: str) -> tuple[Path, StateManager]:
    workflow_path = workspace / "resume_loop.yaml"
    workflow_path.write_text(yaml.safe_dump(_build_resume_loop_workflow(), sort_keys=False))

    state_dir = workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "review_count.txt").write_text("1\n")
    (state_dir / "cycle.txt").write_text("1\n")
    (state_dir / "decision.txt").write_text("REVISE\n")
    (state_dir / "history.log").write_text("review-1\nfix\nincrement-1\n")

    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize("resume_loop.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "ReviewImplementation": {"status": "completed", "exit_code": 0},
        "ImplementationReviewGate": {"status": "failed", "exit_code": 1},
        "ImplementationCycleGate": {"status": "completed", "exit_code": 0},
        "FixImplementation": {"status": "completed", "exit_code": 0},
        "IncrementImplementationCycle": {"status": "completed", "exit_code": 0},
    }
    state_manager._write_state()
    return workflow_path, state_manager


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


@pytest.fixture
def sample_workflow(temp_workspace):
    """Create a sample workflow file."""
    workflow_path = temp_workspace / "test_workflow.yaml"
    workflow_content = """
version: "1.1"
name: Test Resume Workflow
steps:
  - name: Step1
    command: ["echo", "Hello from Step1"]
    output_capture: text
  - name: Step2
    command: ["echo", "Hello from Step2"]
    output_capture: text
  - name: Step3
    command: ["echo", "Hello from Step3"]
    output_capture: text
"""
    workflow_path.write_text(workflow_content)

    # Calculate checksum in StateManager format
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    return workflow_path, checksum


@pytest.fixture
def partial_run_state(temp_workspace, sample_workflow):
    """Create a partial run state with Step1 completed."""
    workflow_path, checksum = sample_workflow
    run_id = "test-run-123"

    # Create state directory
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create state.json
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {
                "status": "completed",
                "exit_code": 0,
                "output": "Hello from Step1",
                "started_at": "2024-01-01T00:00:01Z",
                "completed_at": "2024-01-01T00:00:02Z",
                "duration_ms": 1000
            }
        }
    }

    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))

    return run_id, state_dir


def test_at4_resume_nonexistent_run(temp_workspace):
    """Test resuming a run that doesn't exist."""
    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id="nonexistent-run",
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail


def test_resume_rejects_pre_task6_schema_state(temp_workspace, sample_workflow, capsys):
    """Task 6 should reject resume from pre-identity-schema state without an upgrader."""
    workflow_path, checksum = sample_workflow
    run_id = "old-schema-run"
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
        },
    }, indent=2))

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    captured = capsys.readouterr()
    assert result == 1
    assert "schema version" in captured.err
    assert "1.1.1" in captured.err


def test_at4_resume_completed_run(temp_workspace, sample_workflow):
    """Test resuming a run that has already completed."""
    workflow_path, checksum = sample_workflow
    run_id = "completed-run"

    # Create completed state
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "completed",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
            "Step2": {"status": "completed", "exit_code": 0},
            "Step3": {"status": "completed", "exit_code": 0}
        }
    }

    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False
        )

    assert result == 0  # Should succeed immediately


def test_at4_resume_with_checksum_mismatch(temp_workspace, partial_run_state):
    """Test resume when workflow has been modified."""
    run_id, state_dir = partial_run_state

    # Modify the workflow file
    workflow_path = Path(json.loads((state_dir / "state.json").read_text())["workflow_file"])
    workflow_path.write_text("""
version: "1.1"
name: Modified Workflow
steps:
  - name: Step1
    command: ["echo", "Modified"]
""")

    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail due to checksum mismatch


def test_at4_resume_force_restart(temp_workspace, partial_run_state):
    """Test force restart ignores existing state."""
    run_id, state_dir = partial_run_state

    # Mock the WorkflowExecutor to verify it starts fresh
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'Step1': {'status': 'completed'},
                'Step2': {'status': 'completed'},
                'Step3': {'status': 'completed'}
            }
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=True
            )

        # AT-68: Verify executor was called with resume=False for force_restart
        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs.get('resume') == False

    assert result == 0


def test_at4_resume_corrupted_state_with_repair(temp_workspace, sample_workflow):
    """Test repairing from backup when state is corrupted."""
    workflow_path, checksum = sample_workflow
    run_id = "corrupted-run"

    # Create state directory with backup
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create valid backup
    valid_state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0}
        }
    }

    backup_file = state_dir / "state.json.step_Step1.bak"
    backup_file.write_text(json.dumps(valid_state, indent=2))

    # Create corrupted state file
    (state_dir / "state.json").write_text("{ corrupted json")

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=True,
                force_restart=False
            )

    assert result == 0  # Should succeed after repair

    # Verify state was repaired
    state_content = json.loads((state_dir / "state.json").read_text())
    assert state_content["steps"]["Step1"]["status"] == "completed"


def test_at4_resume_partial_for_each_loop(temp_workspace):
    """Test resuming a partially completed for-each loop."""
    # Create workflow with for-each loop
    workflow_path = temp_workspace / "loop_workflow.yaml"
    workflow_content = """
version: "1.1"
name: Loop Workflow
steps:
  - name: GenerateList
    command: ["echo", "item1\\nitem2\\nitem3"]
    output_capture: lines
  - name: ProcessItems
    for_each:
      items_from: "steps.GenerateList.lines"
      steps:
        - name: ProcessItem
          command: ["echo", "Processing ${item}"]
          output_capture: text
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "loop-run"
    state_dir = temp_workspace / '.orchestrate' / 'runs' / run_id
    state_dir.mkdir(parents=True)

    # Create state with partial loop completion
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"]
            },
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "Processing item1"
            }
            # item2 and item3 not yet processed
        }
    }

    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'GenerateList': {'status': 'completed'},
                'ProcessItems': [
                    {'status': 'completed'},
                    {'status': 'completed'},
                    {'status': 'completed'}
                ]
            }
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False
            )

        # Verify executor was called with resume=True
        assert mock_executor.execute.call_args.kwargs.get('resume') == True

    assert result == 0


def test_resume_partial_for_each_loop_skips_completed_iterations_using_bookkeeping(temp_workspace):
    """Resume should continue from the first incomplete loop iteration without replaying completed work."""
    workflow = {
        "version": "1.1",
        "name": "Loop Resume Workflow",
        "steps": [
            {
                "name": "GenerateList",
                "command": ["bash", "-lc", "printf 'item1\\nitem2\\nitem3\\n'"],
                "output_capture": "lines",
            },
            {
                "name": "ProcessItems",
                "for_each": {
                    "items_from": "steps.GenerateList.lines",
                    "steps": [
                        {
                            "name": "ProcessItem",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p state && printf '%s\\n' \"${item}\" >> state/processed.log",
                            ],
                        }
                    ],
                },
            },
        ],
    }

    workflow_path = temp_workspace / "loop_resume_workflow.yaml"
    workflow_text = yaml.safe_dump(workflow, sort_keys=False)
    workflow_path.write_text(workflow_text)
    checksum = f"sha256:{hashlib.sha256(workflow_text.encode()).hexdigest()}"

    state_dir = temp_workspace / "state"
    state_dir.mkdir()
    (state_dir / "processed.log").write_text("item1\n")

    run_id = "loop-resume-real"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": "loop_resume_workflow.yaml",
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"],
            },
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "item1",
            },
        },
        "for_each": {
            "ProcessItems": {
                "items": ["item1", "item2", "item3"],
                "completed_indices": [0],
                "current_index": 1,
            }
        },
    }
    (run_root / "state.json").write_text(json.dumps(state, indent=2))

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "processed.log").read_text().splitlines() == ["item1", "item2", "item3"]

    resumed = json.loads((run_root / "state.json").read_text())
    assert resumed["for_each"]["ProcessItems"]["completed_indices"] == [0, 1, 2]
    assert resumed["for_each"]["ProcessItems"]["current_index"] is None
    assert len(resumed["steps"]["ProcessItems"]) == 3
    assert resumed["steps"]["ProcessItems[1].ProcessItem"]["status"] == "completed"
    assert resumed["steps"]["ProcessItems[2].ProcessItem"]["status"] == "completed"


def test_resume_partial_for_each_loop_uses_incremental_summary_bookkeeping(temp_workspace):
    """Resume must not treat a partial loop summary as terminal when bookkeeping shows pending iterations."""
    workflow = {
        "version": "1.1",
        "name": "Loop Resume Workflow",
        "steps": [
            {
                "name": "GenerateList",
                "command": ["bash", "-lc", "printf 'item1\\nitem2\\nitem3\\n'"],
                "output_capture": "lines",
            },
            {
                "name": "ProcessItems",
                "for_each": {
                    "items_from": "steps.GenerateList.lines",
                    "steps": [
                        {
                            "name": "ProcessItem",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p state && printf '%s\\n' \"${item}\" >> state/processed.log",
                            ],
                        }
                    ],
                },
            },
        ],
    }

    workflow_path = temp_workspace / "loop_resume_workflow.yaml"
    workflow_text = yaml.safe_dump(workflow, sort_keys=False)
    workflow_path.write_text(workflow_text)
    checksum = f"sha256:{hashlib.sha256(workflow_text.encode()).hexdigest()}"

    state_dir = temp_workspace / "state"
    state_dir.mkdir()
    (state_dir / "processed.log").write_text("item1\n")

    run_id = "loop-resume-incremental-summary"
    run_root = temp_workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": "loop_resume_workflow.yaml",
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "GenerateList": {
                "status": "completed",
                "exit_code": 0,
                "lines": ["item1", "item2", "item3"],
            },
            "ProcessItems": [
                {
                    "ProcessItem": {
                        "status": "completed",
                        "exit_code": 0,
                        "output": "item1",
                    }
                }
            ],
            "ProcessItems[0].ProcessItem": {
                "status": "completed",
                "exit_code": 0,
                "output": "item1",
            },
        },
        "for_each": {
            "ProcessItems": {
                "items": ["item1", "item2", "item3"],
                "completed_indices": [0],
                "current_index": 1,
            }
        },
        "current_step": {
            "name": "ProcessItems",
            "index": 1,
            "status": "running",
            "started_at": "2024-01-01T00:00:30Z",
        },
    }
    (run_root / "state.json").write_text(json.dumps(state, indent=2))

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "processed.log").read_text().splitlines() == ["item1", "item2", "item3"]

    resumed = json.loads((run_root / "state.json").read_text())
    assert resumed["for_each"]["ProcessItems"]["completed_indices"] == [0, 1, 2]
    assert resumed["for_each"]["ProcessItems"]["current_index"] is None
    assert len(resumed["steps"]["ProcessItems"]) == 3
    assert resumed["steps"]["ProcessItems[1].ProcessItem"]["status"] == "completed"
    assert resumed["steps"]["ProcessItems[2].ProcessItem"]["status"] == "completed"


def test_resume_revisits_top_level_review_step_after_fix_loop(temp_workspace):
    """Resume should only skip to the restart point, not skip revisited loop steps forever."""
    run_id = "resume-loop-run"
    _seed_resume_loop_state(temp_workspace, run_id=run_id)

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (temp_workspace / "state" / "review_count.txt").read_text() == "2\n"
    assert (temp_workspace / "state" / "decision.txt").read_text() == "APPROVE\n"
    history = (temp_workspace / "state" / "history.log").read_text()
    assert "review-2\n" in history
    assert "maxed\n" not in history


def test_resume_clears_current_step_after_looped_completion(temp_workspace):
    """Resumed completion should clear any stale current_step metadata."""
    run_id = "resume-loop-current-step"
    _, state_manager = _seed_resume_loop_state(temp_workspace, run_id=run_id)
    assert state_manager.state is not None
    state_manager.state.current_step = {
        "name": "ImplementationReviewGate",
        "index": 1,
        "type": "command",
        "status": "running",
        "started_at": "2024-01-01T00:00:10Z",
        "last_heartbeat_at": "2024-01-01T00:00:11Z",
    }
    state_manager._write_state()

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    payload = json.loads(
        (temp_workspace / ".orchestrate" / "runs" / run_id / "state.json").read_text()
    )
    assert payload["status"] == "completed"
    assert payload.get("current_step") is None


def test_resume_ignores_stale_running_current_step_for_completed_side_effecting_step(temp_workspace):
    """Resume should not rerun a completed side-effecting step just because current_step is stale."""
    workflow_path = temp_workspace / "stale_current_step.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.1",
                "name": "stale-current-step",
                "steps": [
                    {
                        "name": "FixImplementation",
                        "command": ["bash", "-lc", "printf 'fix\\n' >> state/history.log"],
                    },
                    {
                        "name": "NextStep",
                        "command": ["bash", "-lc", "printf 'next\\n' >> state/history.log"],
                    },
                ],
            },
            sort_keys=False,
        )
    )

    state_dir = temp_workspace / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "history.log").write_text("fix\n")

    run_id = "stale-current-step-run"
    state_manager = StateManager(workspace=temp_workspace, run_id=run_id)
    state_manager.initialize("stale_current_step.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.steps = {
        "FixImplementation": {"status": "completed", "exit_code": 0},
        "NextStep": {"status": "pending"},
    }
    state_manager.state.current_step = {
        "name": "FixImplementation",
        "index": 0,
        "type": "command",
        "status": "running",
        "started_at": "2024-01-01T00:00:10Z",
        "last_heartbeat_at": "2024-01-01T00:00:11Z",
    }
    state_manager._write_state()

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    assert result == 0
    assert (state_dir / "history.log").read_text() == "fix\nnext\n"


def test_at4_resume_with_retry_parameters(temp_workspace, partial_run_state):
    """Test resume with custom retry parameters."""
    run_id, state_dir = partial_run_state

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False,
                max_retries=5,
                retry_delay_ms=2000
            )

        # Verify executor was initialized with retry parameters
        MockExecutor.assert_called_once()
        call_kwargs = MockExecutor.call_args.kwargs
        assert call_kwargs.get('max_retries') == 5
        assert call_kwargs.get('retry_delay_ms') == 2000

    assert result == 0


def test_resume_preserves_control_flow_counters(temp_workspace):
    """Resume keeps persisted cycle-guard counters available to the executor."""
    workflow_path = temp_workspace / "control_flow_resume.yaml"
    workflow_content = """
version: "1.8"
name: Control Flow Resume Workflow
max_transitions: 5
steps:
  - name: Step1
    max_visits: 3
    command: ["echo", "Hello from Step1"]
  - name: Step2
    command: ["echo", "Hello from Step2"]
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "control-flow-run"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "suspended",
        "context": {},
        "steps": {
            "Step1": {"status": "completed", "exit_code": 0},
        },
        "transition_count": 1,
        "step_visits": {"Step1": 1},
    }, indent=2))

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'Step1': {'status': 'completed'},
                'Step2': {'status': 'completed'},
            },
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(run_id=run_id)

        state_manager = MockExecutor.call_args.kwargs['state_manager']
        assert state_manager.state.transition_count == 1
        assert state_manager.state.step_visits == {"Step1": 1}

    assert result == 0


def test_resume_defaults_retry_settings_for_provider_steps(temp_workspace):
    """Resume normalizes retry defaults before constructing the executor."""
    workflow_path = temp_workspace / "provider_resume.yaml"
    workflow_content = """
version: "1.1"
name: Provider Resume Workflow
providers:
  test_provider:
    command: ["echo", "${PROMPT}"]
steps:
  - name: ProviderStep
    provider: test_provider
"""
    workflow_path.write_text(workflow_content)
    checksum = f"sha256:{hashlib.sha256(workflow_content.encode()).hexdigest()}"

    run_id = "provider-resume-run"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": str(workflow_path),
        "workflow_checksum": checksum,
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "failed",
        "context": {},
        "steps": {
            "ProviderStep": {"status": "failed", "exit_code": 1},
        },
    }, indent=2))

    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {
                'ProviderStep': {'status': 'completed', 'exit_code': 0},
            },
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            result = resume_workflow(run_id=run_id)

        constructor_kwargs = MockExecutor.call_args.kwargs
        assert constructor_kwargs['max_retries'] == 0
        assert constructor_kwargs['retry_delay_ms'] == 1000

        execute_kwargs = mock_executor.execute.call_args.kwargs
        assert execute_kwargs['max_retries'] == 0
        assert execute_kwargs['retry_delay_ms'] == 1000

    assert result == 0


def test_at4_resume_displays_progress_information(temp_workspace, partial_run_state, capsys):
    """Test that resume command displays progress information."""
    run_id, state_dir = partial_run_state

    # Add more steps to state
    state = json.loads((state_dir / "state.json").read_text())
    state["steps"]["Step2"] = {"status": "failed", "exit_code": 1}
    (state_dir / "state.json").write_text(json.dumps(state, indent=2))

    # Mock WorkflowExecutor
    with patch('orchestrator.cli.commands.resume.WorkflowExecutor') as MockExecutor:
        mock_executor = MagicMock()
        mock_executor.execute.return_value = {
            'status': 'completed',
            'steps': {}
        }
        MockExecutor.return_value = mock_executor

        with patch('os.getcwd', return_value=str(temp_workspace)):
            resume_workflow(
                run_id=run_id,
                repair=False,
                force_restart=False
            )

    captured = capsys.readouterr()
    assert "Resuming run test-run-123" in captured.out
    assert "Completed steps: Step1" in captured.out
    assert "Pending steps: Step2" in captured.out
