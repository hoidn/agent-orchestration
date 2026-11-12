"""Dashboard run projection from scanned evaluated views.

Inputs are `RunRecord` values from `RunScanner`: an evaluated view (`load_evaluated_view`), an
unreadable candidate (read or parse error), or a retired run (no evaluated authority). Outputs are
`DashboardIndexRow` and `DashboardRunDetail` read models. A retired run's old state is never read.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from orchestrator.dashboard.attempt_files import attempt_file_refs
from orchestrator.dashboard.cursor import ExecutionCursorProjector
from orchestrator.dashboard.files import FileReferenceResolver
from orchestrator.dashboard.models import (
    DashboardIndexRow,
    DashboardRunDetail,
    DashboardStep,
    RunRecord,
)
from orchestrator.workflow.evaluated.authority import PROFILE
from orchestrator.workflow.evaluated.views import retired_run_refusal


class RunProjector:
    """Build dashboard index/detail models from scanner records."""

    def __init__(self, *, now: Optional[datetime] = None) -> None:
        self.now = now or datetime.now(timezone.utc)
        self.cursor_projector = ExecutionCursorProjector()

    def project_detail(self, run: RunRecord, *, attempt_files: bool = True) -> DashboardRunDetail:
        """Detail model; `attempt_files=False` skips listing attempt directories (pages that link no files)."""
        if run.state is not None and run.state.get("result_persistence_profile") == PROFILE:
            return self._project_evaluated_detail(run, attempt_files)
        if run.retired:
            refusal = retired_run_refusal(run.run_dir_id)
            return DashboardRunDetail(row=self._row(run, "retired", refusal, [refusal]), warnings=[refusal])
        failure = "failed to parse state" if run.parse_error else "failed to read state"
        reason = run.parse_error or run.read_error or failure
        warnings = list(run.warnings) + [reason]
        return DashboardRunDetail(row=self._row(run, "unreadable", f"{failure}: {reason}", warnings),
                                  warnings=warnings)

    def project_index(self, runs: list[RunRecord]) -> list[DashboardIndexRow]:
        return [self.project_detail(run, attempt_files=False).row for run in runs]

    def _project_evaluated_detail(self, run: RunRecord, attempt_files: bool) -> DashboardRunDetail:
        state = dict(run.state)
        resolver = FileReferenceResolver(run.workspace.root, run.run_root)
        warnings = list(run.warnings)
        steps = [self._evaluated_step(identity, payload, resolver, warnings, attempt_files)
                 for identity, payload in state["steps"].items()]
        cursor = self.cursor_projector.project(state)
        row = DashboardIndexRow(
            workspace_id=run.workspace.id, workspace_label=run.workspace.label,
            workspace_root=run.workspace.root, run_dir_id=run.run_dir_id,
            run_root=run.run_root, state_path=run.state_path, state_run_id=run.state_run_id,
            workflow_file=state["workflow_file"], display_status=state["status"],
            started_at=state["started_at"], updated_at=state["updated_at"],
            elapsed_seconds=self._elapsed_seconds(state), read_time=self.now.isoformat(),
            cursor_summary=cursor.summary,
            failure_summary=self._failure_summary(state, steps), warnings=warnings,
        )
        return DashboardRunDetail(row=row, steps=steps, cursor=cursor, bound_inputs=state["bound_inputs"],
            workflow_outputs=state["workflow_outputs"], error=state["error"], state=state, warnings=warnings)

    def _evaluated_step(self, identity, payload, resolver, warnings, attempt_files):
        return DashboardStep(ref=identity, name=identity, step_id=identity,
            kind=payload["effect_class"], status=payload["status"],
            duration_ms=payload.get("duration_ms"), error=payload.get("error"),
            outcome=payload.get("host_settlement"),
            file_refs=attempt_file_refs(payload, resolver, warnings) if attempt_files else {},
            output_preview=json.dumps(payload["value"], ensure_ascii=False)[:200] if "value" in payload else "",
            attempt=payload.get("attempt"), started_at=payload.get("started_at"),
            completed_at=payload.get("completed_at"))

    def _row(self, run: RunRecord, status: str, failure: str, warnings: list[str]) -> DashboardIndexRow:
        """Index row for a run without a readable evaluated view."""
        return DashboardIndexRow(
            workspace_id=run.workspace.id, workspace_label=run.workspace.label,
            workspace_root=run.workspace.root, run_dir_id=run.run_dir_id, run_root=run.run_root,
            state_path=run.state_path, state_run_id=run.state_run_id, display_status=status,
            read_time=self.now.isoformat(), failure_summary=failure, warnings=warnings,
        )

    def _failure_summary(self, state: Mapping[str, Any], steps: list[DashboardStep]) -> str:
        run_error = state.get("error")
        if isinstance(run_error, Mapping):
            message = run_error.get("message") or run_error.get("type")
            if isinstance(message, str) and message:
                return message
        for step in steps:
            if step.status == "failed" and isinstance(step.error, Mapping):
                message = step.error.get("message") or step.error.get("type")
                if isinstance(message, str) and message:
                    return message
        return ""

    def _elapsed_seconds(self, state: Mapping[str, Any]) -> Optional[float]:
        """From `started_at` to `updated_at` (the last memo record), or to now while the run is running."""
        start = self._parse_datetime(state.get("started_at"))
        end = self.now if state.get("status") == "running" else self._parse_datetime(state.get("updated_at"))
        if start is None or end is None:
            return None
        return max(0.0, (end - start).total_seconds())

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
