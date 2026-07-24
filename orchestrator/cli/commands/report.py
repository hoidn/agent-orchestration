"""Report command implementation."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from orchestrator.observability.report import (
    _load_typed_terminal_observability_summary,
    derive_status_projection,
    render_status_markdown,
)
from orchestrator.runtime_observability import compute_active_runtime


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
) -> dict[str, Any]:
    """Build a report exclusively from persisted run state and run-owned evidence."""

    def result_status(value: Any) -> str:
        if isinstance(value, Mapping):
            status = value.get("status")
            if isinstance(status, str):
                return status
            if value.get("skipped"):
                return "skipped"
            exit_code = value.get("exit_code")
            if exit_code == 0:
                return "completed"
            if isinstance(exit_code, int):
                return "failed"
            child_statuses = [
                result_status(child)
                for child in value.values()
                if isinstance(child, (Mapping, list))
            ]
            if "failed" in child_statuses:
                return "failed"
            if "running" in child_statuses:
                return "running"
            if child_statuses and all(
                status in {"completed", "skipped"} for status in child_statuses
            ):
                return "completed"
        elif isinstance(value, list):
            child_statuses = [result_status(child) for child in value]
            if "failed" in child_statuses:
                return "failed"
            if "running" in child_statuses:
                return "running"
            if child_statuses and all(
                status in {"completed", "skipped"} for status in child_statuses
            ):
                return "completed"
        return "pending"

    def step_entry(name: str, value: Any) -> dict[str, Any]:
        payload = value if isinstance(value, Mapping) else {}
        raw_preview = payload.get("output")
        if raw_preview is None:
            raw_preview = payload.get("text")
        preview = str(raw_preview) if raw_preview is not None else ""
        if len(preview) > 200:
            preview = preview[:197] + "..."
        return {
            "name": name,
            "step_id": payload.get("step_id"),
            "kind": payload.get("type") or "unknown",
            "status": result_status(value),
            "input": {},
            "output": {
                "exit_code": payload.get("exit_code"),
                "duration_ms": payload.get("duration_ms"),
                "output_preview": preview,
                "artifacts": (
                    payload.get("artifacts")
                    if isinstance(payload.get("artifacts"), Mapping)
                    else {}
                ),
                "error": payload.get("error"),
                "outcome": payload.get("outcome"),
            },
        }

    raw_steps = state.get("steps")
    steps = (
        [step_entry(str(name), value) for name, value in raw_steps.items()]
        if isinstance(raw_steps, Mapping)
        else []
    )
    current_step = (
        state.get("current_step")
        if isinstance(state.get("current_step"), dict)
        else None
    )
    if isinstance(current_step, dict):
        current_name = str(
            current_step.get("name")
            or current_step.get("step_id")
            or "current_step"
        )
        existing = next((step for step in steps if step["name"] == current_name), None)
        if existing is None:
            existing = step_entry(current_name, current_step)
            steps.append(existing)
        existing["status"] = current_step.get("status") or "running"

    status_projection = derive_status_projection(state, steps)
    display_status = str(status_projection["display_status"])
    progress = {
        "total": len(steps),
        "completed": sum(1 for step in steps if step["status"] == "completed"),
        "running": sum(1 for step in steps if step["status"] == "running"),
        "failed": sum(1 for step in steps if step["status"] == "failed"),
        "pending": sum(1 for step in steps if step["status"] == "pending"),
        "skipped": sum(1 for step in steps if step["status"] == "skipped"),
    }
    if display_status == "completed":
        progress["running"] = 0
        progress["failed"] = 0
        progress["pending"] = 0
        progress["completed"] = progress["total"] - progress["skipped"]
    elif display_status == "failed":
        progress["running"] = 0

    run_payload: dict[str, Any] = {
        "run_id": state.get("run_id"),
        "status": display_status,
        "workflow_file": state.get("workflow_file"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "run_root": str(run_dir),
        "transition_count": state.get("transition_count", 0),
        "persisted_status": status_projection["persisted_status"],
        "display_status": display_status,
        "display_status_reason": status_projection["display_status_reason"],
        "report_warning": (
            "Authored workflow definitions are not loaded for report projection; "
            "showing a state-only report."
        ),
    }
    status_reason = status_projection["display_status_reason"]
    if status_reason:
        run_payload["status_reason"] = status_reason
    if isinstance(state.get("bound_inputs"), Mapping):
        run_payload["bound_inputs"] = state["bound_inputs"]
    if isinstance(state.get("workflow_outputs"), Mapping):
        run_payload["workflow_outputs"] = state["workflow_outputs"]
    if isinstance(state.get("finalization"), Mapping) and state["finalization"]:
        run_payload["finalization"] = state["finalization"]
    if isinstance(state.get("error"), Mapping):
        run_payload["error"] = state["error"]
    typed_terminal_summary = _load_typed_terminal_observability_summary(run_dir)
    if typed_terminal_summary is not None:
        run_payload["observability_summaries"] = {
            "typed_terminal": typed_terminal_summary,
        }
    run_payload.update(compute_active_runtime(state))

    return {"run": run_payload, "progress": progress, "steps": steps}


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

    snapshot = _state_only_snapshot(state, run_dir)
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

    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    return 0
