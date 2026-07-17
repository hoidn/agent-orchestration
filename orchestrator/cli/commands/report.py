"""Report command implementation."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from orchestrator.loader import WorkflowLoader
from orchestrator.observability.report import build_status_snapshot, render_status_markdown
from orchestrator.workflow.linting import lint_workflow, render_lint_markdown


def _latest_run_dir(runs_root: Path) -> Optional[Path]:
    if not runs_root.exists():
        return None
    candidates = [p for p in runs_root.iterdir() if p.is_dir() and (p / "state.json").exists()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def _resolve_run_dir(run_id: Optional[str], runs_root: Path) -> Optional[Path]:
    if run_id:
        run_dir = runs_root / run_id
        if (run_dir / "state.json").exists():
            return run_dir
        return None
    return _latest_run_dir(runs_root)


def _state_only_snapshot(
    state: dict[str, Any],
    run_dir: Path,
    *,
    load_error: str,
) -> dict[str, Any]:
    """Build a minimal report snapshot when the workflow definition is unavailable."""
    current_step = (
        state.get("current_step")
        if isinstance(state.get("current_step"), dict)
        else None
    )
    steps = []
    if isinstance(current_step, dict):
        steps.append(
            {
                "name": current_step.get("name") or current_step.get("step_id") or "current_step",
                "step_id": current_step.get("step_id"),
                "kind": current_step.get("type") or "unknown",
                "status": current_step.get("status") or "unknown",
                "input": {},
                "output": {},
            }
        )
    status = str(state.get("status") or "unknown")
    return {
        "run": {
            "run_id": state.get("run_id"),
            "status": status,
            "workflow_file": state.get("workflow_file"),
            "started_at": state.get("started_at"),
            "updated_at": state.get("updated_at"),
            "run_root": str(run_dir),
            "persisted_status": status,
            "display_status": status,
            "display_status_reason": "state_only_report",
            "error": state.get("error") if isinstance(state.get("error"), dict) else None,
            "report_warning": (
                "Workflow definition could not be loaded for report projection; "
                f"showing state-only report: {load_error}"
            ),
        },
        "progress": {
            "total": len(steps),
            "completed": 0,
            "running": 0,
            "failed": sum(1 for step in steps if step.get("status") == "failed"),
            "pending": 0,
            "skipped": 0,
        },
        "steps": steps,
    }


def report_workflow(
    run_id: Optional[str] = None,
    runs_root: str = ".orchestrate/runs",
    format: str = "md",
    output: Optional[str] = None,
) -> int:
    """Render a workflow status report for an existing run."""
    runs_root_path = Path(runs_root)
    run_dir = _resolve_run_dir(run_id, runs_root_path)
    if run_dir is None:
        print("Error: run not found", file=sys.stderr)
        return 1

    state_file = run_dir / "state.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error: failed to load state: {exc}", file=sys.stderr)
        return 1

    workflow_file = state.get("workflow_file")
    if not isinstance(workflow_file, str) or not workflow_file:
        print("Error: state missing workflow_file", file=sys.stderr)
        return 1

    workflow_path = Path(workflow_file)
    if not workflow_path.is_absolute():
        workflow_path = Path.cwd() / workflow_path

    if not workflow_path.exists():
        print(f"Error: workflow file not found: {workflow_path}", file=sys.stderr)
        return 1

    load_error: Optional[str] = None
    try:
        workflow = WorkflowLoader(
            Path.cwd(),
            emit_yaml_deprecation_warning=False,
        ).load_bundle(workflow_path)
    except Exception as exc:
        workflow = None
        load_error = str(exc)

    lint_warnings = lint_workflow(workflow) if workflow is not None else []
    if workflow is None:
        snapshot = _state_only_snapshot(state, run_dir, load_error=load_error or "unknown")
    else:
        snapshot = build_status_snapshot(workflow, state, run_dir)
    if lint_warnings:
        snapshot["lint"] = {"warnings": lint_warnings}
    run_snapshot = snapshot.get("run", {})
    original_status = state.get("status")
    derived_status = run_snapshot.get("status")
    status_reason = run_snapshot.get("status_reason")

    # Self-heal stale "running" runs once a deterministic terminal status is inferred.
    if (
        original_status == "running"
        and derived_status in {"completed", "failed"}
        and derived_status != original_status
    ):
        state["status"] = derived_status
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        if not isinstance(state.get("context"), dict):
            state["context"] = {}
        if status_reason:
            state["context"]["status_reconciled_reason"] = status_reason
            state["context"]["status_reconciled_at"] = state["updated_at"]
        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        run_snapshot["updated_at"] = state["updated_at"]

    if format == "json":
        rendered = json.dumps(snapshot, indent=2) + "\n"
    else:
        rendered = render_status_markdown(snapshot)
        report_warning = snapshot.get("run", {}).get("report_warning")
        if isinstance(report_warning, str) and report_warning:
            rendered = f"{rendered.rstrip()}\n\n> {report_warning}\n"
        if lint_warnings:
            rendered = f"{rendered.rstrip()}\n\n{render_lint_markdown(lint_warnings)}\n"

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    return 0
