from pathlib import Path

import json

from tests.workflow_fixture_loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from tests.workflow_bundle_helpers import bundle_context_dict


def _write_workflow(workspace: Path, payload: dict) -> Path:
    path = workspace / "workflow.yaml"
    path.write_text(json.dumps(payload, sort_keys=False), encoding="utf-8")
    return path


def _run_workflow(workspace: Path, payload: dict, provided_inputs: dict | None = None) -> dict:
    workflow_path = _write_workflow(workspace, payload)
    loaded = WorkflowLoader(workspace).load(workflow_path)
    bound_inputs = bind_workflow_inputs(
        workflow_input_contracts(loaded),
        provided_inputs or {},
        workspace,
    )
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        context=bundle_context_dict(loaded),
        bound_inputs=bound_inputs,
    )
    return WorkflowExecutor(loaded, workspace, state_manager).execute(on_error="continue")


def test_provider_field_can_resolve_from_workflow_input(tmp_path: Path):
    (tmp_path / "prompt.md").write_text("Say hello.", encoding="utf-8")
    workflow = {
        "version": "2.7",
        "name": "dynamic-provider-test",
        "inputs": {
            "selected_provider": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["alpha", "beta"],
                "default": "beta",
            }
        },
        "providers": {
            "alpha": {
                "command": ["bash", "-lc", "printf alpha"],
                "input_mode": "stdin",
            },
            "beta": {
                "command": ["bash", "-lc", "printf beta"],
                "input_mode": "stdin",
            },
        },
        "steps": [
            {
                "name": "Ask",
                "provider": "${inputs.selected_provider}",
                "input_file": "prompt.md",
                "output_capture": "text",
            }
        ],
    }

    result = _run_workflow(tmp_path, workflow)

    assert result["steps"]["Ask"]["status"] == "completed"
    assert result["steps"]["Ask"]["output"] == "beta"


def test_provider_field_reports_unknown_resolved_provider(tmp_path: Path):
    (tmp_path / "prompt.md").write_text("Say hello.", encoding="utf-8")
    workflow = {
        "version": "2.7",
        "name": "dynamic-provider-missing-test",
        "inputs": {
            "selected_provider": {
                "kind": "scalar",
                "type": "enum",
                "allowed": ["missing"],
                "default": "missing",
            }
        },
        "providers": {
            "alpha": {
                "command": ["bash", "-lc", "printf alpha"],
                "input_mode": "stdin",
            },
        },
        "steps": [
            {
                "name": "Ask",
                "provider": "${inputs.selected_provider}",
                "input_file": "prompt.md",
                "output_capture": "text",
            }
        ],
    }

    result = _run_workflow(tmp_path, workflow)

    assert result["steps"]["Ask"]["status"] == "failed"
    assert result["steps"]["Ask"]["exit_code"] == 2
    assert result["steps"]["Ask"]["error"]["type"] == "provider_not_found"
    assert result["steps"]["Ask"]["error"]["context"]["provider"] == "missing"
