"""Deterministic workflow status reporting."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from orchestrator.workflow.loaded_bundle import workflow_bundle


_PREVIEW_LIMIT = 200
_STALE_RUNNING_TIMEOUT_SEC = 300


def _resolved_current_step_name(workflow: Any, current_step: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(current_step, dict):
        return None
    bundle = workflow_bundle(workflow)
    if bundle is not None:
        step_id = current_step.get("step_id")
        if isinstance(step_id, str) and step_id:
            projected_name = bundle.projection.presentation_key_for_step_id(step_id)
            if isinstance(projected_name, str) and projected_name:
                return projected_name
    name = current_step.get("name")
    return name if isinstance(name, str) and name else None


def _normalize_output_preview(step_result: Dict[str, Any]) -> str:
    for key in ("text", "output"):
        value = step_result.get(key)
        if isinstance(value, str) and value:
            return value[:_PREVIEW_LIMIT]
    lines = step_result.get("lines")
    if isinstance(lines, list):
        text = "\n".join(str(line) for line in lines)
        return text[:_PREVIEW_LIMIT]
    payload = step_result.get("json")
    if payload is not None:
        text = str(payload)
        return text[:_PREVIEW_LIMIT]
    return ""


def _report_compatible_value(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_report_compatible_value(item) for item in value]
    if isinstance(value, list):
        return [_report_compatible_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _report_compatible_value(item) for key, item in value.items()}
    return value


def _read_prompt_audit(run_root: Path, step_name: str) -> Optional[str]:
    prompt_file = run_root / "logs" / f"{step_name}.prompt.txt"
    if not prompt_file.exists():
        return None
    try:
        return prompt_file.read_text(encoding="utf-8")
    except OSError:
        return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_step_status(step_result: Any) -> Optional[str]:
    if isinstance(step_result, dict):
        status = step_result.get("status")
        if isinstance(status, str) and status:
            return status
        if step_result.get("skipped"):
            return "skipped"
        exit_code = step_result.get("exit_code")
        if exit_code == 0:
            return "completed"
        if isinstance(exit_code, int):
            return "failed"
        child_statuses = [_coerce_step_status(value) for value in step_result.values()]
        if child_statuses and all(status in {"completed", "failed", "skipped"} for status in child_statuses):
            return "completed"
    elif isinstance(step_result, list):
        # for_each summary arrays are considered complete if all iterations settled.
        child_statuses = [_coerce_step_status(item) for item in step_result]
        if child_statuses and all(status in {"completed", "failed", "skipped"} for status in child_statuses):
            return "completed"
        return "running"
    return None


def derive_status_projection(
    state: Mapping[str, Any],
    step_entries: list[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Optional[str]]:
    """Derive display status from state without mutating the input."""
    status = state.get("status")
    persisted_status = str(status)
    display_status = persisted_status
    display_status_reason: Optional[str] = None

    if status != "running":
        return {
            "persisted_status": persisted_status,
            "display_status": display_status,
            "display_status_reason": display_status_reason,
        }

    if now is None:
        now = datetime.now(timezone.utc)
    current_step = state.get("current_step")

    if isinstance(current_step, dict):
        heartbeat = _parse_iso_datetime(
            current_step.get("last_heartbeat_at") or current_step.get("started_at")
        )
        if heartbeat is not None and (now - heartbeat).total_seconds() > _STALE_RUNNING_TIMEOUT_SEC:
            display_status = "failed"
            display_status_reason = "stale_running_step_heartbeat_timeout"
        return {
            "persisted_status": persisted_status,
            "display_status": display_status,
            "display_status_reason": display_status_reason,
        }

    updated_at = _parse_iso_datetime(state.get("updated_at"))
    if updated_at is None:
        return {
            "persisted_status": persisted_status,
            "display_status": display_status,
            "display_status_reason": display_status_reason,
        }

    if (now - updated_at).total_seconds() <= _STALE_RUNNING_TIMEOUT_SEC:
        return {
            "persisted_status": persisted_status,
            "display_status": display_status,
            "display_status_reason": display_status_reason,
        }

    step_statuses = {entry.get("status") for entry in step_entries}
    if "pending" in step_statuses or "running" in step_statuses:
        display_status = "failed"
        display_status_reason = "stale_running_without_current_step"
    if "failed" in step_statuses:
        display_status = "failed"
        display_status_reason = "stale_running_terminal_not_finalized"
    elif display_status_reason is None:
        display_status = "completed"
        display_status_reason = "stale_running_terminal_not_finalized"
    return {
        "persisted_status": persisted_status,
        "display_status": display_status,
        "display_status_reason": display_status_reason,
    }


def _derive_run_status(state: Dict[str, Any], step_entries: list[Dict[str, Any]]) -> tuple[str, Optional[str]]:
    projection = derive_status_projection(state, step_entries)
    return str(projection["display_status"]), projection["display_status_reason"]


def build_status_snapshot(
    workflow: Any,
    state: Dict[str, Any],
    run_root: Path,
    run_log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build a deterministic status snapshot from workflow + state artifacts."""
    bundle = workflow_bundle(workflow)
    if bundle is None:
        raise TypeError("build_status_snapshot requires a LoadedWorkflowBundle")
    steps_state = state.get("steps") if isinstance(state.get("steps"), dict) else {}
    step_visits = state.get("step_visits") if isinstance(state.get("step_visits"), dict) else {}
    current_step = state.get("current_step") if isinstance(state.get("current_step"), dict) else None
    current_step_name = _resolved_current_step_name(workflow, current_step)

    step_entries = []
    for node_id in bundle.projection.ordered_execution_node_ids():
        projection_entry = bundle.projection.entries_by_node_id.get(node_id)
        if projection_entry is None:
            continue
        definition = projection_entry.step_definition
        name = projection_entry.presentation_key
        result = steps_state.get(name, {}) if isinstance(steps_state, dict) else {}
        prompt_text = _read_prompt_audit(run_root, name)
        is_current_step = current_step_name == name

        status = _coerce_step_status(result) or "pending"
        if is_current_step:
            status = "running"
        if status == "pending" and prompt_text:
            status = "running"

        entry = {
            "name": name,
            "step_id": (
                result.get("step_id")
                if isinstance(result, dict) and isinstance(result.get("step_id"), str)
                else projection_entry.step_id
            ),
            "kind": definition.report_kind,
            "status": status,
            "consumes": _report_compatible_value(definition.consumes),
            "expected_outputs": _report_compatible_value(definition.expected_outputs),
            "visit_count": step_visits.get(name),
            "current_visit_count": current_step.get("visit_count") if is_current_step else None,
            "last_result_visit_count": result.get("visit_count") if isinstance(result, dict) else None,
            "max_visits": definition.max_visits,
            "input": {},
            "output": {},
        }

        if definition.provider is not None:
            entry["input"]["provider"] = definition.provider
            if prompt_text is not None:
                entry["input"]["prompt"] = prompt_text
        if definition.command is not None:
            entry["input"]["command"] = _report_compatible_value(definition.command)

        if isinstance(result, dict) and result:
            entry["output"] = {
                "exit_code": result.get("exit_code"),
                "duration_ms": result.get("duration_ms"),
                "output_preview": _normalize_output_preview(result),
                "artifacts": result.get("artifacts", {}),
                "error": result.get("error"),
                "outcome": result.get("outcome"),
            }
            debug_payload = result.get("debug")
            if isinstance(debug_payload, dict) and debug_payload:
                entry["output"]["debug"] = debug_payload
            if isinstance(debug_payload, dict) and isinstance(debug_payload.get("call"), dict):
                entry["output"]["call"] = debug_payload.get("call")
            if isinstance(debug_payload, dict) and isinstance(debug_payload.get("provider_session"), dict):
                entry["output"]["provider_session"] = debug_payload.get("provider_session")

        if status == "completed":
            entry["summary"] = "completed"
        elif status == "running":
            entry["summary"] = "in progress"
        elif status == "failed":
            entry["summary"] = "failed"
        elif status == "skipped":
            entry["summary"] = "skipped"
        else:
            entry["summary"] = "pending"

        step_entries.append(entry)

    progress = {
        "total": len(step_entries),
        "completed": sum(1 for s in step_entries if s["status"] == "completed"),
        "running": sum(1 for s in step_entries if s["status"] == "running"),
        "failed": sum(1 for s in step_entries if s["status"] == "failed"),
        "skipped": sum(1 for s in step_entries if s["status"] == "skipped"),
    }
    progress["pending"] = (
        progress["total"]
        - progress["completed"]
        - progress["running"]
        - progress["failed"]
        - progress["skipped"]
    )

    status_projection = derive_status_projection(state, step_entries)
    run_status = str(status_projection["display_status"])
    status_reason = status_projection["display_status_reason"]
    if run_status != "running":
        if run_status == "completed":
            progress["running"] = 0
            progress["failed"] = 0
            progress["pending"] = 0
            progress["completed"] = progress["total"] - progress["skipped"]
        elif run_status == "failed":
            progress["running"] = 0

    run_payload = {
        "run_id": state.get("run_id"),
        "status": run_status,
        "workflow_file": state.get("workflow_file"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "run_root": str(run_root),
        "run_log_path": str(run_log_path) if run_log_path else None,
        "transition_count": state.get("transition_count", 0),
        "max_transitions": bundle.surface.max_transitions,
        "persisted_status": status_projection["persisted_status"],
        "display_status": status_projection["display_status"],
        "display_status_reason": status_projection["display_status_reason"],
    }
    if status_reason:
        run_payload["status_reason"] = status_reason
    if isinstance(state.get("bound_inputs"), dict):
        run_payload["bound_inputs"] = state.get("bound_inputs", {})
    if isinstance(state.get("workflow_outputs"), dict):
        run_payload["workflow_outputs"] = state.get("workflow_outputs", {})
    if isinstance(state.get("finalization"), dict) and state.get("finalization"):
        run_payload["finalization"] = state.get("finalization")
    if isinstance(state.get("error"), dict):
        run_payload["error"] = state.get("error")

    return {
        "run": {
            **run_payload,
        },
        "progress": progress,
        "steps": step_entries,
    }


def _render_kv_lines(items: Iterable[tuple[str, Any]]) -> str:
    return "\n".join(f"- {key}: `{value}`" for key, value in items)


def render_status_markdown(snapshot: Dict[str, Any]) -> str:
    """Render snapshot to a human-readable markdown report."""
    run = snapshot.get("run", {})
    progress = snapshot.get("progress", {})
    lines = [
        "# Workflow Status",
        "",
        "## Run",
        _render_kv_lines(
            [
                ("run_id", run.get("run_id")),
                ("status", run.get("status")),
                ("workflow_file", run.get("workflow_file")),
                ("started_at", run.get("started_at")),
                ("updated_at", run.get("updated_at")),
            ]
        ),
        "",
    ]

    bound_inputs = run.get("bound_inputs")
    if isinstance(bound_inputs, dict) and bound_inputs:
        lines.extend([
            "## Inputs",
            _render_kv_lines(sorted(bound_inputs.items())),
            "",
        ])

    workflow_outputs = run.get("workflow_outputs")
    if isinstance(workflow_outputs, dict) and workflow_outputs:
        lines.extend([
            "## Outputs",
            _render_kv_lines(sorted(workflow_outputs.items())),
            "",
        ])

    run_error = run.get("error")
    if isinstance(run_error, dict) and run_error:
        lines.extend([
            "## Run Error",
            _render_kv_lines(
                [
                    ("type", run_error.get("type")),
                    ("message", run_error.get("message")),
                ]
            ),
        ])
        context = run_error.get("context")
        if isinstance(context, dict) and context:
            lines.append("- context:")
            for key, value in sorted(context.items()):
                lines.append(f"  - {key}: `{value}`")
        lines.append("")

    lines.extend([
        "## Progress",
        _render_kv_lines(
            [
                ("total", progress.get("total", 0)),
                ("completed", progress.get("completed", 0)),
                ("running", progress.get("running", 0)),
                ("failed", progress.get("failed", 0)),
                ("pending", progress.get("pending", 0)),
                ("skipped", progress.get("skipped", 0)),
            ]
        ),
        "",
        "## Steps",
    ])

    for step in snapshot.get("steps", []):
        lines.append(f"### {step.get('name')} ({step.get('status')})")
        lines.append(f"- kind: `{step.get('kind')}`")

        input_payload = step.get("input", {})
        if input_payload:
            lines.append("- input:")
            if "provider" in input_payload:
                lines.append(f"  - provider: `{input_payload['provider']}`")
            if "command" in input_payload:
                lines.append(f"  - command: `{input_payload['command']}`")
            if "prompt" in input_payload:
                lines.append("  - prompt:")
                lines.append("```")
                lines.append(str(input_payload["prompt"]))
                lines.append("```")

        output_payload = step.get("output", {})
        if output_payload:
            lines.append("- output:")
            lines.append(f"  - exit_code: `{output_payload.get('exit_code')}`")
            lines.append(f"  - duration_ms: `{output_payload.get('duration_ms')}`")
            preview = output_payload.get("output_preview")
            if preview:
                lines.append("  - preview:")
                lines.append("```")
                lines.append(str(preview))
                lines.append("```")
            artifacts = output_payload.get("artifacts")
            if artifacts:
                lines.append(f"  - artifacts: `{artifacts}`")
            debug_payload = output_payload.get("debug")
            if debug_payload:
                lines.append(f"  - debug: `{debug_payload}`")
            provider_session = output_payload.get("provider_session")
            if provider_session:
                lines.append(f"  - provider_session: `{provider_session}`")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
