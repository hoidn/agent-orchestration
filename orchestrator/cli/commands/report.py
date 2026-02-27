"""Report command implementation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from orchestrator.loader import WorkflowLoader
from orchestrator.observability.report import build_status_snapshot, render_status_markdown


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

    try:
        workflow = WorkflowLoader(Path.cwd()).load(workflow_path)
    except Exception as exc:
        print(f"Error: failed to load workflow: {exc}", file=sys.stderr)
        return 1

    snapshot = build_status_snapshot(workflow, state, run_dir)

    if format == "json":
        rendered = json.dumps(snapshot, indent=2) + "\n"
    else:
        rendered = render_status_markdown(snapshot)

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    return 0
