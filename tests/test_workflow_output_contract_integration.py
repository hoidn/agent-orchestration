"""Integration tests for expected_outputs enforcement in workflow execution."""

from types import SimpleNamespace
from pathlib import Path

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _write_workflow(workspace: Path, workflow: dict) -> Path:
    workflow_file = workspace / "workflow.yaml"
    workflow_file.write_text(yaml.dump(workflow))
    return workflow_file


def test_command_step_fails_when_expected_output_missing(tmp_path: Path):
    """Missing expected output file converts a successful step into contract_violation."""
    workflow = {
        "version": "1.1.1",
        "name": "contract-missing",
        "steps": [{
            "name": "DraftPlan",
            "command": ["bash", "-lc", "echo done"],
            "expected_outputs": [{
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "docs/plans",
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")

    result = state["steps"]["DraftPlan"]
    assert result["exit_code"] == 2
    assert result["status"] == "failed"
    assert result["error"]["type"] == "contract_violation"


def test_command_step_persists_artifacts_when_contract_is_valid(tmp_path: Path):
    """Validated artifacts are persisted under steps.<name>.artifacts."""
    workflow = {
        "version": "1.1.1",
        "name": "contract-valid",
        "steps": [{
            "name": "DraftPlan",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/plans && "
                "printf 'docs/plans/plan-a.md\\n' > state/plan_pointer.txt && "
                "printf '# plan\\n' > docs/plans/plan-a.md",
            ],
            "expected_outputs": [{
                "path": "state/plan_pointer.txt",
                "type": "relpath",
                "under": "docs/plans",
                "must_exist_target": True,
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()
    result = state["steps"]["DraftPlan"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {"plan_pointer": "docs/plans/plan-a.md"}

    persisted = state_manager.load().to_dict()["steps"]["DraftPlan"]
    assert persisted["artifacts"] == {"plan_pointer": "docs/plans/plan-a.md"}


def test_provider_step_persists_artifacts_when_contract_is_valid(tmp_path: Path):
    """Provider steps are also gated by expected_outputs and persist artifacts."""
    workflow = {
        "version": "1.1.1",
        "name": "provider-contract-valid",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "expected_outputs": [{
                "path": "state/review_decision.txt",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            }],
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    executor.provider_executor.prepare_invocation = lambda *args, **kwargs: (SimpleNamespace(), None)

    def _fake_execute(_invocation):
        (tmp_path / "state").mkdir(exist_ok=True)
        (tmp_path / "state" / "review_decision.txt").write_text("APPROVE\n")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.execute = _fake_execute

    state = executor.execute()
    result = state["steps"]["Review"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {"review_decision": "APPROVE"}
