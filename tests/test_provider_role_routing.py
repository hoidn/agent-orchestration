from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from tests.workflow_bundle_helpers import bundle_context_dict


def _write_workflow(workspace: Path, payload: dict) -> Path:
    path = workspace / "workflow.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
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


def _copy_neurips_implementation_phase(workspace: Path) -> Path:
    repo_root = Path(__file__).resolve().parent.parent
    for relpath in [
        "workflows/library/neurips_backlog_implementation_phase.yaml",
        "workflows/library/scripts/run_neurips_backlog_checks.py",
        "workflows/library/prompts/neurips_backlog_implementation_phase/implement_implementation.md",
        "workflows/library/prompts/neurips_backlog_implementation_phase/review_implementation.md",
        "workflows/library/prompts/neurips_backlog_implementation_phase/fix_implementation.md",
    ]:
        src = repo_root / relpath
        dest = workspace / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return workspace / "workflows/library/neurips_backlog_implementation_phase.yaml"


def _prepare_implementation_phase_inputs(workspace: Path) -> dict:
    (workspace / "docs/plans").mkdir(parents=True, exist_ok=True)
    (workspace / "state").mkdir(parents=True, exist_ok=True)
    (workspace / "docs/plans/design.md").write_text("# Design\n", encoding="utf-8")
    (workspace / "docs/plans/plan.md").write_text("# Plan\n", encoding="utf-8")
    (workspace / "state/checks.json").write_text('["true"]\n', encoding="utf-8")
    return {
        "state_root": "state/implementation",
        "design_path": "docs/plans/design.md",
        "plan_path": "docs/plans/plan.md",
        "check_commands_path": "state/checks.json",
        "execution_report_target_path": "artifacts/work/execution.md",
        "checks_report_target_path": "artifacts/checks/checks.json",
        "implementation_review_report_target_path": "artifacts/review/implementation-review.md",
    }


def _run_neurips_implementation_phase_with_mocked_providers(
    workspace: Path,
    provider_inputs: dict | None = None,
) -> list[str]:
    workflow_path = _copy_neurips_implementation_phase(workspace)
    loaded = WorkflowLoader(workspace).load(workflow_path)
    raw_inputs = _prepare_implementation_phase_inputs(workspace)
    raw_inputs.update(provider_inputs or {})
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(loaded), raw_inputs, workspace)
    state_manager = StateManager(workspace=workspace, run_id="test-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        context=bundle_context_dict(loaded),
        bound_inputs=bound_inputs,
    )
    executor = WorkflowExecutor(loaded, workspace, state_manager)
    provider_names: list[str] = []
    call_index = {"value": 0}

    def _prepare_invocation(_self, *args, **kwargs):
        provider_names.append(kwargs["provider_name"])
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", "")), None

    def _execute(_self, _invocation, **_kwargs):
        index = call_index["value"]
        call_index["value"] += 1
        state_root = workspace / "state/implementation"
        execution_report = workspace / "artifacts/work/execution.md"
        review_report = workspace / "artifacts/review/implementation-review.md"
        execution_report.parent.mkdir(parents=True, exist_ok=True)
        review_report.parent.mkdir(parents=True, exist_ok=True)
        state_root.mkdir(parents=True, exist_ok=True)

        if index == 0:
            execution_report.write_text("# Execution\n", encoding="utf-8")
            (state_root / "implementation_state.json").write_text(
                '{"implementation_state":"COMPLETED","execution_report_path":"artifacts/work/execution.md"}\n',
                encoding="utf-8",
            )
        elif index == 1:
            review_report.write_text("# Review revise\n", encoding="utf-8")
            (state_root / "implementation_review_report_path.txt").write_text(
                "artifacts/review/implementation-review.md\n",
                encoding="utf-8",
            )
            (state_root / "implementation_review_decision.txt").write_text("REVISE\n", encoding="utf-8")
        elif index == 2:
            execution_report.write_text("# Execution fixed\n", encoding="utf-8")
        elif index == 3:
            review_report.write_text("# Review approve\n", encoding="utf-8")
            (state_root / "implementation_review_report_path.txt").write_text(
                "artifacts/review/implementation-review.md\n",
                encoding="utf-8",
            )
            (state_root / "implementation_review_decision.txt").write_text("APPROVE\n", encoding="utf-8")
        else:
            raise AssertionError(f"unexpected provider call {index}")

        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute()

    assert state["status"] == "completed"
    return provider_names


def test_neurips_implementation_phase_routes_execute_provider_from_input(tmp_path: Path):
    provider_names = _run_neurips_implementation_phase_with_mocked_providers(
        tmp_path,
        {
            "implementation_execute_provider": "claude_opus",
            "implementation_review_provider": "codex",
            "implementation_fix_provider": "codex",
        },
    )

    assert provider_names == ["claude_opus", "codex", "codex", "codex"]


def test_neurips_implementation_phase_defaults_to_codex_providers(tmp_path: Path):
    provider_names = _run_neurips_implementation_phase_with_mocked_providers(tmp_path)

    assert provider_names == ["codex", "codex", "codex", "codex"]
