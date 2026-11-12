"""Report command implementation.

Reads evaluated runs only, through `load_evaluated_view` and `report_snapshot`. A run directory with
a `state.json` entry and no evaluated authority was written by the retired runtime: `report` refuses it
with one stderr line and exit 2, and never opens its `state.json` beyond the view-hint check in
`has_evaluated_authority`. Without `--run-id`, the latest evaluated run by directory name is reported.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from orchestrator.observability.report import render_status_markdown
from orchestrator.workflow.evaluated.views import (
    has_evaluated_authority,
    load_evaluated_view,
    report_snapshot,
    retired_run_refusal,
)


def _latest_run_dir(runs_root: Path) -> Optional[Path]:
    if not runs_root.exists():
        return None
    candidates = [p for p in runs_root.iterdir() if p.is_dir() and has_evaluated_authority(p)]
    return max(candidates, key=lambda p: p.name) if candidates else None


def _resolve_run_dir(run_id: Optional[str], runs_root: Path) -> Optional[Path]:
    if not run_id:
        return _latest_run_dir(runs_root)
    run_dir = runs_root / run_id
    if has_evaluated_authority(run_dir) or os.path.lexists(run_dir / "state.json"):
        return run_dir
    return None


def report_workflow(
    run_id: Optional[str] = None,
    runs_root: str = ".orchestrate/runs",
    format: str = "md",
    output: Optional[str] = None,
) -> int:
    """Render a workflow status report for an existing evaluated run."""
    run_dir = _resolve_run_dir(run_id, Path(runs_root))
    if run_dir is None:
        print("Error: run not found", file=sys.stderr)
        return 1
    if not has_evaluated_authority(run_dir):
        print(f"Error: {retired_run_refusal(run_dir.name)}", file=sys.stderr)
        return 2
    try:
        snapshot = report_snapshot(load_evaluated_view(run_dir), run_dir)
    except (OSError, ValueError) as exc:
        print(f"Error: memo_inconsistent: {exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(snapshot, indent=2) + "\n" if format == "json" else render_status_markdown(snapshot)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0
