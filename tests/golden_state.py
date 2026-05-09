from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs


ROOT = Path(__file__).resolve().parents[1]


def load_expected_observation(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_fixture_workflow(
    *, fixture_root: Path, workspace: Path, workflow_relpath: str, scenario_name: str
) -> dict[str, Any]:
    shutil.copytree(fixture_root, workspace, dirs_exist_ok=True)
    fake_provider_dest = workspace / "tests/fixtures/bin/fake_provider.py"
    fake_provider_dest.parent.mkdir(parents=True, exist_ok=True)
    fake_provider_dest.write_text(
        (ROOT / "tests/fixtures/bin/fake_provider.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    scenario_path = fixture_root / "scenarios" / f"{scenario_name}.json"
    if scenario_path.is_file():
        _write_provider_scenario(workspace, json.loads(scenario_path.read_text(encoding="utf-8")))
    else:
        _write_provider_scenario(workspace, {"mode": scenario_name})

    state = _execute_workflow(
        workspace=workspace,
        workflow_relpath=workflow_relpath,
        inputs={},
    )
    return _build_observation(workspace, state)


def run_neurips_workspace_workflow(
    *, fixture_root: Path, workspace: Path, workflow_relpath: str, scenario_name: str
) -> dict[str, Any]:
    shutil.copytree(fixture_root, workspace, dirs_exist_ok=True)
    _copy_neurips_runtime_files(workspace)

    scenario = json.loads((fixture_root / "scenarios" / f"{scenario_name}.json").read_text(encoding="utf-8"))
    _write_provider_scenario(workspace, scenario["provider"])

    with _codex_shim_on_path(workspace):
        state = _execute_workflow(
            workspace=workspace,
            workflow_relpath=workflow_relpath,
            inputs=scenario["workflow_inputs"],
        )
    return _build_observation(workspace, state)


def _write_provider_scenario(workspace: Path, scenario: dict[str, Any]) -> None:
    target = workspace / "state/fake_provider_scenario.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(scenario, indent=2) + "\n", encoding="utf-8")


def _copy_neurips_runtime_files(workspace: Path) -> None:
    relpaths = [
        "workflows/examples/neurips_steered_backlog_drain.yaml",
        "workflows/library/neurips_backlog_selector.yaml",
        "workflows/library/neurips_backlog_gap_drafter.yaml",
        "workflows/library/neurips_backlog_roadmap_sync_phase.yaml",
        "workflows/library/neurips_backlog_seeded_plan_phase.yaml",
        "workflows/library/neurips_backlog_implementation_phase.yaml",
        "workflows/library/neurips_selected_backlog_item.yaml",
        "workflows/library/scripts/build_neurips_backlog_manifest.py",
        "workflows/library/scripts/materialize_neurips_selected_item_inputs.py",
        "workflows/library/scripts/move_neurips_backlog_item.py",
        "workflows/library/scripts/recover_neurips_plan_gate_outputs.py",
        "workflows/library/scripts/reconcile_neurips_selected_item.py",
        "workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py",
        "workflows/library/scripts/validate_neurips_backlog_gap_draft.py",
        "workflows/library/scripts/run_neurips_backlog_checks.py",
        "workflows/library/scripts/update_neurips_backlog_run_state.py",
    ]
    relpaths.extend(
        path.relative_to(ROOT).as_posix() for path in (ROOT / "workflows/library/prompts").rglob("*.md")
    )
    for relpath in sorted(set(relpaths)):
        src = ROOT / relpath
        dest = workspace / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


@contextlib.contextmanager
def _codex_shim_on_path(workspace: Path):
    bin_dir = workspace / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim_path = bin_dir / "codex"
    shim_path.write_text(
        "#!/usr/bin/env bash\n"
        f'exec "{sys.executable}" "{(ROOT / "tests/fixtures/bin/fake_provider.py").as_posix()}" "$@"\n',
        encoding="utf-8",
    )
    shim_path.chmod(shim_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir.as_posix()}:{old_path}" if old_path else bin_dir.as_posix()
    try:
        yield
    finally:
        os.environ["PATH"] = old_path


def _execute_workflow(*, workspace: Path, workflow_relpath: str, inputs: dict[str, Any]) -> dict[str, Any]:
    loader = WorkflowLoader(workspace)
    workflow_path = workspace / workflow_relpath
    workflow = loader.load(workflow_path)
    bound_inputs = bind_workflow_inputs(workflow_input_contracts(workflow), inputs, workspace)
    state_manager = StateManager(workspace=workspace, run_id="oracle-run")
    state_manager.initialize(workflow_relpath, _thaw(workflow_context(workflow)), bound_inputs=bound_inputs)
    return WorkflowExecutor(workflow, workspace, state_manager).execute(on_error="continue")


def _thaw(value: Any) -> Any:
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


def _build_observation(workspace: Path, state: dict[str, Any]) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relpath = path.relative_to(workspace).as_posix()
        if _is_interesting_file(relpath):
            files[relpath] = _file_observation(path, workspace)

    queue = {
        "active": sorted(path.name for path in (workspace / "docs/backlog/active").glob("*.md"))
        if (workspace / "docs/backlog/active").is_dir()
        else [],
        "in_progress": sorted(path.name for path in (workspace / "docs/backlog/in_progress").glob("*.md"))
        if (workspace / "docs/backlog/in_progress").is_dir()
        else [],
        "done": sorted(path.name for path in (workspace / "docs/backlog/done").glob("*.md"))
        if (workspace / "docs/backlog/done").is_dir()
        else [],
    }

    return {
        "status": state.get("status"),
        "workflow_outputs": _normalize_value(state.get("workflow_outputs", {}), workspace),
        "steps": {
            name: {
                "status": step.get("status"),
                "artifacts": _normalize_value(step.get("artifacts", {}), workspace),
                "error": _normalize_value(step.get("error"), workspace),
            }
            for name, step in sorted(state.get("steps", {}).items())
            if _is_interesting_step(name, step)
        },
        "queue": queue,
        "files": files,
    }


def _is_interesting_file(relpath: str) -> bool:
    if relpath.startswith("artifacts/") and relpath.endswith((".json", ".md")):
        return True
    if relpath.startswith("docs/backlog/") and relpath.endswith(".md"):
        return True
    if not relpath.startswith("state/") or not relpath.endswith(".json"):
        return False
    interesting_names = {
        "fake_provider_scenario.json",
        "implementation_state.json",
        "selection.json",
        "selected-item-inputs.json",
        "selected-item-outcome.json",
        "final_plan_gate.json",
        "progress_ledger.json",
        "run_state.json",
        "materialized.json",
        "invalid_selection.json",
        "missing_target.json",
    }
    return Path(relpath).name in interesting_names


def _is_interesting_step(name: str, step: dict[str, Any]) -> bool:
    if step.get("error") is not None:
        return True
    if "[" not in name:
        return True
    interesting_fragments = (
        "SelectNextItem",
        "ResolveItemSelection",
        "RouteItemSelection",
        "RunSelectedItem",
        "PublishDrainSummary",
    )
    return any(fragment in name for fragment in interesting_fragments)


def _file_observation(path: Path, workspace: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        return {"json": _normalize_value(json.loads(path.read_text(encoding="utf-8")), workspace)}
    return {
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_value(value: Any, workspace: Path) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_value(item, workspace) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize_value(item, workspace) for item in value]
    if isinstance(value, str):
        return _normalize_text(value, workspace)
    return value


def _normalize_text(value: str, workspace: Path) -> str:
    normalized = value.replace(workspace.as_posix(), "<workspace>")
    normalized = normalized.replace("oracle-run", "<run-id>")
    normalized = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", "<timestamp>", normalized)
    normalized = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00", "<timestamp>", normalized)
    return normalized
