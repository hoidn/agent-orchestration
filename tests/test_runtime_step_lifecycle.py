"""Integration tests for runtime step lifecycle state updates."""

import hashlib
import json
import threading
import time
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow), encoding="utf-8")
    return workflow_file


def test_long_running_step_updates_current_step_heartbeat(tmp_path: Path):
    workflow = {
        "version": "1.1.1",
        "name": "runtime-step-lifecycle",
        "steps": [
            {
                "name": "LongCommand",
                "command": ["bash", "-lc", "python -c 'import time; time.sleep(0.6)'"],
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(
        loaded,
        tmp_path,
        state_manager,
        step_heartbeat_interval_sec=0.1,
    )

    worker = threading.Thread(target=executor.execute)
    worker.start()

    state_file = tmp_path / ".orchestrate" / "runs" / "test-run" / "state.json"
    deadline = time.time() + 5
    running_snapshot = None
    while time.time() < deadline:
        if state_file.exists():
            snapshot = json.loads(state_file.read_text(encoding="utf-8"))
            current = snapshot.get("current_step")
            if isinstance(current, dict) and current.get("name") == "LongCommand":
                running_snapshot = snapshot
                break
        time.sleep(0.02)

    assert running_snapshot is not None
    first_heartbeat = running_snapshot["current_step"]["last_heartbeat_at"]

    time.sleep(0.25)
    second_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    assert second_snapshot.get("current_step", {}).get("name") == "LongCommand"
    assert second_snapshot["current_step"]["last_heartbeat_at"] != first_heartbeat

    worker.join(timeout=5)
    assert not worker.is_alive()

    final_snapshot = json.loads(state_file.read_text(encoding="utf-8"))
    assert final_snapshot.get("current_step") is None
    assert final_snapshot["steps"]["LongCommand"]["status"] == "completed"


def test_assert_gate_persists_failed_outcome(tmp_path: Path):
    workflow = {
        "version": "1.5",
        "name": "assert-lifecycle",
        "steps": [
            {
                "name": "Gate",
                "assert": {
                    "equals": {
                        "left": "APPROVE",
                        "right": "REVISE",
                    }
                },
                "on": {"failure": {"goto": "_end"}},
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="assert-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    gate = state["steps"]["Gate"]
    assert gate["status"] == "failed"
    assert gate["exit_code"] == 3
    assert gate["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "assert_failed",
        "retryable": False,
    }


def test_provider_pre_execution_failures_normalize_before_typed_routing(tmp_path: Path):
    workflow = {
        "version": "1.6",
        "name": "provider-pre-execution-lifecycle",
        "providers": {
            "write_file": {
                "command": [
                    "bash",
                    "-lc",
                    "printf '%s' \"${value}\" > state/provider-ran.txt",
                ]
            }
        },
        "steps": [
            {
                "name": "UseProvider",
                "provider": "write_file",
                "provider_params": {
                    "value": "${context.missing_value}",
                },
                "on": {"failure": {"goto": "CheckFailure"}},
            },
            {
                "name": "CheckFailure",
                "assert": {
                    "all_of": [
                        {
                            "compare": {
                                "left": {"ref": "root.steps.UseProvider.outcome.phase"},
                                "op": "eq",
                                "right": "pre_execution",
                            }
                        },
                        {
                            "compare": {
                                "left": {"ref": "root.steps.UseProvider.outcome.class"},
                                "op": "eq",
                                "right": "pre_execution_failed",
                            }
                        },
                    ]
                },
            },
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="provider-pre-execution-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")

    provider_step = state["steps"]["UseProvider"]
    assert provider_step["status"] == "failed"
    assert provider_step["error"]["type"] == "substitution_error"
    assert provider_step["outcome"] == {
        "status": "failed",
        "phase": "pre_execution",
        "class": "pre_execution_failed",
        "retryable": False,
    }
    assert not (tmp_path / "state" / "provider-ran.txt").exists()
    assert state["steps"]["CheckFailure"]["status"] == "completed"


def test_set_scalar_persists_local_artifacts_in_step_state(tmp_path: Path):
    workflow = {
        "version": "1.7",
        "name": "set-scalar-lifecycle",
        "artifacts": {
            "failed_count": {
                "kind": "scalar",
                "type": "integer",
            }
        },
        "steps": [
            {
                "name": "InitializeCount",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 1,
                },
            }
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="set-scalar-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()

    assert state["steps"]["InitializeCount"]["status"] == "completed"
    assert state["steps"]["InitializeCount"]["artifacts"] == {"failed_count": 1}


def test_resume_skips_only_until_restart_point_not_after_loop_back(tmp_path: Path):
    workflow = {
        "version": "1.1",
        "name": "resume-loop-runtime",
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

    workflow_file = _write_workflow(tmp_path, workflow)
    state_dir = tmp_path / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "review_count.txt").write_text("1\n")
    (state_dir / "cycle.txt").write_text("1\n")
    (state_dir / "decision.txt").write_text("REVISE\n")
    (state_dir / "history.log").write_text("review-1\nfix\nincrement-1\n")

    state_manager = StateManager(workspace=tmp_path, run_id="resume-loop-runtime")
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.workflow_checksum = f"sha256:{hashlib.sha256(workflow_file.read_bytes()).hexdigest()}"
    state_manager.state.steps = {
        "ReviewImplementation": {"status": "completed", "exit_code": 0},
        "ImplementationReviewGate": {"status": "failed", "exit_code": 1},
        "ImplementationCycleGate": {"status": "completed", "exit_code": 0},
        "FixImplementation": {"status": "completed", "exit_code": 0},
        "IncrementImplementationCycle": {"status": "completed", "exit_code": 0},
    }
    state_manager._write_state()
    state_manager.load()

    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)
    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(resume=True)

    assert state["status"] == "completed"
    assert (state_dir / "review_count.txt").read_text() == "2\n"
    history = (state_dir / "history.log").read_text()
    assert "review-2\n" in history
    assert "maxed\n" not in history


def test_resume_restart_index_skips_completed_top_level_for_each(tmp_path: Path):
    workflow = {
        "version": "1.1",
        "name": "resume-foreach-restart",
        "steps": [
            {"name": "Generate", "command": ["bash", "-lc", "printf 'generate\\n' >> state/history.log"]},
            {
                "name": "Loop",
                "for_each": {
                    "items": ["a", "b"],
                    "steps": [
                        {
                            "name": "Inner",
                            "command": ["bash", "-lc", "printf 'inner-${item}\\n' >> state/history.log"],
                        }
                    ],
                },
            },
            {"name": "After", "command": ["bash", "-lc", "printf 'after\\n' >> state/history.log"]},
        ],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="resume-foreach-run")
    state_manager.initialize("workflow.yaml")
    assert state_manager.state is not None
    state_manager.state.status = "failed"
    state_manager.state.workflow_checksum = f"sha256:{hashlib.sha256(workflow_file.read_bytes()).hexdigest()}"
    state_manager.state.steps = {
        "Generate": {"status": "completed", "exit_code": 0},
        "Loop": [{"status": "completed"}, {"status": "completed"}],
        "Loop[0].Inner": {"status": "completed", "exit_code": 0},
        "Loop[1].Inner": {"status": "completed", "exit_code": 0},
        "After": {"status": "failed", "exit_code": 1},
    }
    state_manager._write_state()

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    restart_index = executor._determine_resume_restart_index(state_manager.load().to_dict())

    assert restart_index == 2
