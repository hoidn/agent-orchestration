import json
import shutil
from dataclasses import is_dataclass
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs


ROOT = Path(__file__).resolve().parents[1]


def _copy_repo_file(workspace: Path, relpath: str) -> None:
    src = ROOT / relpath
    dest = workspace / relpath
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _thaw(value):
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): _thaw(item) for key, item in value.items()}
    if is_dataclass(value):
        return {str(key): _thaw(item) for key, item in vars(value).items()}
    return value


def _bundle_context_dict(bundle) -> dict:
    return _thaw(workflow_context(bundle))


def test_non_progress_step_back_demo_records_and_continues(tmp_path):
    workspace = tmp_path / "workspace"
    for relpath in [
        "workflows/examples/non_progress_step_back_demo.yaml",
        "workflows/library/scripts/evaluate_workflow_non_progress.py",
        "workflows/library/scripts/record_workflow_step_back_outcome.py",
        "workflows/library/scripts/write_workflow_non_progress_demo_inputs.py",
    ]:
        _copy_repo_file(workspace, relpath)

    workflow_path = workspace / "workflows/examples/non_progress_step_back_demo.yaml"
    loader = WorkflowLoader(workspace)
    workflow = loader.load(workflow_path)
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), {}, workspace)
    state_manager = StateManager(workspace=workspace, run_id="demo-run")
    state_manager.initialize(
        workflow_path.relative_to(workspace).as_posix(),
        _bundle_context_dict(workflow),
        bound_inputs=bound_inputs,
    )

    state = WorkflowExecutor(workflow, workspace, state_manager).execute()

    assert state["status"] == "completed"
    assert state["workflow_outputs"]["drain_status"] == "CONTINUE"
    summary = json.loads((workspace / "artifacts/work/non-progress-step-back-demo/summary.json").read_text())
    assert summary["record_status"] == "STEP_BACK_RECORDED"
    assert summary["action"] == "FIX_WORKFLOW_MECHANICS"
    run_state = json.loads((workspace / "state/non-progress-step-back-demo/run_state.json").read_text())
    assert run_state["history"][-1]["event"] == "step_back"
