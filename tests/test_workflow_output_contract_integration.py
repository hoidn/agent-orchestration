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
                "name": "plan_pointer",
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
                "name": "plan_pointer",
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


def test_command_step_can_disable_artifact_persistence_in_state(tmp_path: Path):
    """expected_outputs can be validated without duplicating artifact values in state.json."""
    workflow = {
        "version": "1.1.1",
        "name": "contract-valid-no-persist",
        "steps": [{
            "name": "SelectBacklogItem",
            "command": [
                "bash",
                "-lc",
                "mkdir -p state docs/backlog && "
                "printf 'docs/backlog/item-001.md\\n' > state/backlog_item_path.txt && "
                "printf '# item\\n' > docs/backlog/item-001.md",
            ],
            "persist_artifacts_in_state": False,
            "expected_outputs": [{
                "name": "backlog_item_path",
                "path": "state/backlog_item_path.txt",
                "type": "relpath",
                "under": "docs/backlog",
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
    result = state["steps"]["SelectBacklogItem"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert "artifacts" not in result

    persisted = state_manager.load().to_dict()["steps"]["SelectBacklogItem"]
    assert "artifacts" not in persisted


def test_provider_step_persists_artifacts_when_contract_is_valid(tmp_path: Path):
    """Provider steps are also gated by expected_outputs and persist artifacts."""
    workflow = {
        "version": "1.1.1",
        "name": "provider-contract-valid",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "expected_outputs": [{
                "name": "review_decision",
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

    def _fake_execute(_invocation, **_kwargs):
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


def test_provider_failure_preserves_original_error_and_skips_contract(tmp_path: Path):
    """Provider execution failures must not be replaced by contract_violation errors."""
    workflow = {
        "version": "1.1.1",
        "name": "provider-contract-failure-preserve",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "expected_outputs": [{
                "name": "review_decision",
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

    def _failing_execute(_invocation, **_kwargs):
        return SimpleNamespace(
            exit_code=1,
            stdout=b"provider failed",
            stderr=b"boom",
            duration_ms=1,
            error={"type": "execution_failed", "message": "Provider execution failed"},
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
        )

    executor.provider_executor.execute = _failing_execute

    state = executor.execute(on_error="continue")
    result = state["steps"]["Review"]

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["error"]["type"] == "execution_failed"
    assert "artifacts" not in result
    assert result["error"]["type"] != "contract_violation"


def test_command_step_persists_artifacts_from_output_bundle(tmp_path: Path):
    """v1.3 output_bundle fields are validated and persisted as step artifacts."""
    workflow = {
        "version": "1.3",
        "name": "bundle-command-valid",
        "steps": [{
            "name": "AssessExecutionCompletion",
            "command": [
                "bash",
                "-lc",
                "mkdir -p artifacts/work docs/plans && "
                "printf '# plan\\n' > docs/plans/plan-a.md && "
                "printf '{\"plan_path\":\"docs/plans/plan-a.md\",\"failed_count\":0}\\n' > artifacts/work/summary.json",
            ],
            "output_bundle": {
                "path": "artifacts/work/summary.json",
                "fields": [
                    {
                        "name": "plan_path",
                        "json_pointer": "/plan_path",
                        "type": "relpath",
                        "under": "docs/plans",
                        "must_exist_target": True,
                    },
                    {
                        "name": "failed_count",
                        "json_pointer": "/failed_count",
                        "type": "integer",
                    },
                ],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute()
    result = state["steps"]["AssessExecutionCompletion"]

    assert result["exit_code"] == 0
    assert result["status"] == "completed"
    assert result["artifacts"] == {
        "plan_path": "docs/plans/plan-a.md",
        "failed_count": 0,
    }


def test_command_step_output_bundle_contract_violation_sets_exit_2(tmp_path: Path):
    """Missing output_bundle file converts successful command to contract_violation."""
    workflow = {
        "version": "1.3",
        "name": "bundle-command-missing",
        "steps": [{
            "name": "AssessExecutionCompletion",
            "command": ["bash", "-lc", "echo done"],
            "output_bundle": {
                "path": "artifacts/work/summary.json",
                "fields": [{
                    "name": "status",
                    "json_pointer": "/status",
                    "type": "enum",
                    "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                }],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")
    result = state["steps"]["AssessExecutionCompletion"]

    assert result["exit_code"] == 2
    assert result["status"] == "failed"
    assert result["error"]["type"] == "contract_violation"


def test_provider_step_persists_artifacts_from_output_bundle(tmp_path: Path):
    """Provider steps can satisfy deterministic contracts via output_bundle in v1.3."""
    workflow = {
        "version": "1.3",
        "name": "bundle-provider-valid",
        "steps": [{
            "name": "Review",
            "provider": "codex",
            "output_bundle": {
                "path": "artifacts/work/review.json",
                "fields": [{
                    "name": "review_decision",
                    "json_pointer": "/review_decision",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    executor.provider_executor.prepare_invocation = lambda *args, **kwargs: (SimpleNamespace(), None)

    def _fake_execute(_invocation, **_kwargs):
        (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
        (tmp_path / "artifacts" / "work" / "review.json").write_text('{"review_decision":"APPROVE"}\n')
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


def test_nonzero_exit_skips_output_bundle_validation(tmp_path: Path):
    """Failed process exit should preserve original failure and skip bundle validation."""
    workflow = {
        "version": "1.3",
        "name": "bundle-skip-on-failure",
        "steps": [{
            "name": "AssessExecutionCompletion",
            "command": ["bash", "-lc", "echo fail && exit 1"],
            "output_bundle": {
                "path": "artifacts/work/summary.json",
                "fields": [{
                    "name": "status",
                    "json_pointer": "/status",
                    "type": "enum",
                    "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                }],
            },
        }],
    }

    workflow_file = _write_workflow(tmp_path, workflow)
    loader = WorkflowLoader(tmp_path)
    loaded = loader.load(workflow_file)

    state_manager = StateManager(workspace=tmp_path, run_id="test-run")
    state_manager.initialize("workflow.yaml")

    executor = WorkflowExecutor(loaded, tmp_path, state_manager)
    state = executor.execute(on_error="continue")
    result = state["steps"]["AssessExecutionCompletion"]

    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert "artifacts" not in result
    assert result.get("error", {}).get("type") != "contract_violation"
