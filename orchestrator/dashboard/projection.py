"""Dashboard run projection from scanned state files."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from orchestrator.dashboard.cursor import ExecutionCursorProjector
from orchestrator.dashboard.files import FileReferenceResolver, UnsafePathError
from orchestrator.dashboard.models import (
    DashboardIndexRow,
    DashboardRunDetail,
    DashboardStep,
    FileReference,
    RunRecord,
)
from orchestrator.loader import WorkflowLoader
from orchestrator.observability.report import build_status_snapshot, derive_status_projection


class RunProjector:
    """Build dashboard index/detail models from scanner records."""

    def __init__(self, *, now: Optional[datetime] = None) -> None:
        self.now = now or datetime.now(timezone.utc)
        self.cursor_projector = ExecutionCursorProjector()

    def project_detail(self, run: RunRecord) -> DashboardRunDetail:
        read_time = self.now.isoformat()
        base_warnings = list(run.warnings)
        if run.state is None:
            failure = "failed to parse state" if run.parse_error else "failed to read state"
            detail_warnings = base_warnings + [run.parse_error or run.read_error or failure]
            row = self._row(
                run,
                read_time=read_time,
                persisted_status="unknown",
                display_status="unreadable",
                failure_summary=f"{failure}: {run.parse_error or run.read_error or ''}".rstrip(),
                warnings=detail_warnings,
            )
            return DashboardRunDetail(row=row, warnings=detail_warnings, degraded=True)

        state = copy.deepcopy(dict(run.state))
        resolver = FileReferenceResolver(run.workspace.root, run.run_root)
        workflow, workflow_name, workflow_warning = self._load_workflow(run, state, resolver)
        warnings = base_warnings + ([workflow_warning] if workflow_warning else [])

        if workflow is not None:
            snapshot = build_status_snapshot(workflow, state, run.run_root)
            steps = self._steps_from_snapshot(snapshot.get("steps", []), resolver, warnings)
            run_payload = snapshot.get("run", {}) if isinstance(snapshot.get("run"), Mapping) else {}
            persisted_status = str(run_payload.get("persisted_status") or state.get("status"))
            display_status = str(run_payload.get("display_status") or run_payload.get("status"))
            display_status_reason = self._str_or_none(run_payload.get("display_status_reason"))
            degraded = False
        else:
            steps = self._steps_from_state(state, resolver, warnings)
            status_projection = derive_status_projection(
                state,
                [{"status": step.status} for step in steps],
                now=self.now,
            )
            persisted_status = str(status_projection["persisted_status"])
            display_status = str(status_projection["display_status"])
            display_status_reason = status_projection["display_status_reason"]
            degraded = True

        cursor = self.cursor_projector.project(state)
        warnings.extend(cursor.warnings)
        artifact_versions = self._artifact_versions(state, resolver, warnings)
        observability_files = self._observability_files(run.run_root, resolver, warnings)
        common_artifact_refs = self._common_artifact_refs(steps, artifact_versions)
        failure_summary = self._failure_summary(state, steps, run.parse_error or run.read_error)
        row = self._row(
            run,
            read_time=read_time,
            persisted_status=persisted_status,
            display_status=display_status,
            display_status_reason=display_status_reason,
            cursor_summary=cursor.summary,
            workflow_file=self._str_or_none(state.get("workflow_file")),
            workflow_name=workflow_name,
            failure_summary=failure_summary,
            warnings=warnings,
            availability=self._availability(run.run_root),
        )
        return DashboardRunDetail(
            row=row,
            steps=steps,
            cursor=cursor,
            bound_inputs=state.get("bound_inputs", {}) if isinstance(state.get("bound_inputs"), Mapping) else {},
            workflow_outputs=(
                state.get("workflow_outputs", {})
                if isinstance(state.get("workflow_outputs"), Mapping)
                else {}
            ),
            finalization=state.get("finalization", {}) if isinstance(state.get("finalization"), Mapping) else {},
            error=state.get("error"),
            artifact_versions=artifact_versions,
            artifact_consumes=(
                state.get("artifact_consumes", {})
                if isinstance(state.get("artifact_consumes"), Mapping)
                else {}
            ),
            observability_files=observability_files,
            common_artifact_refs=common_artifact_refs,
            warnings=warnings,
            degraded=degraded,
            state=state,
        )

    def project_index(self, runs: list[RunRecord]) -> list[DashboardIndexRow]:
        return [self.project_detail(run).row for run in runs]

    def _load_workflow(
        self,
        run: RunRecord,
        state: Mapping[str, Any],
        resolver: FileReferenceResolver,
    ) -> tuple[Any, Optional[str], Optional[str]]:
        workflow_file = state.get("workflow_file")
        if not isinstance(workflow_file, str) or not workflow_file:
            return None, None, "state missing workflow_file"
        workflow_path = Path(workflow_file)
        try:
            if workflow_path.is_absolute():
                resolved = workflow_path.resolve(strict=False)
                try:
                    resolved.relative_to(run.workspace.root)
                except ValueError:
                    return None, None, f"workflow file is outside workspace: {workflow_file}"
            else:
                ref = resolver.workspace_ref(workflow_file)
                if ref.status != "ok":
                    return None, None, f"workflow file is not readable: {workflow_file}"
                resolved = ref.absolute_path
        except UnsafePathError as exc:
            return None, None, f"workflow file is unsafe: {exc}"

        try:
            workflow = WorkflowLoader(run.workspace.root).load_bundle(resolved)
        except Exception as exc:
            return None, None, f"failed to load workflow metadata: {exc}"
        workflow_name = getattr(getattr(workflow, "surface", None), "name", None)
        return workflow, workflow_name if isinstance(workflow_name, str) else None, None

    def _steps_from_snapshot(
        self,
        snapshot_steps: Any,
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> list[DashboardStep]:
        steps: list[DashboardStep] = []
        if not isinstance(snapshot_steps, list):
            return steps
        for entry in snapshot_steps:
            if not isinstance(entry, Mapping):
                continue
            output = entry.get("output") if isinstance(entry.get("output"), Mapping) else {}
            artifacts = output.get("artifacts") if isinstance(output.get("artifacts"), Mapping) else {}
            name = str(entry.get("name") or "")
            debug = output.get("debug") if isinstance(output.get("debug"), Mapping) else {}
            provider_session = (
                output.get("provider_session")
                if isinstance(output.get("provider_session"), Mapping)
                else debug.get("provider_session")
                if isinstance(debug.get("provider_session"), Mapping)
                else {}
            )
            visit_count = self._first_present(
                entry.get("last_result_visit_count"),
                entry.get("visit_count"),
                entry.get("current_visit_count"),
            )
            steps.append(
                DashboardStep(
                    ref=self._step_ref(name, entry.get("step_id")),
                    name=name,
                    step_id=self._str_or_none(entry.get("step_id")),
                    kind=str(entry.get("kind") or "unknown"),
                    status=str(entry.get("status") or "unknown"),
                    visit_count=visit_count,
                    duration_ms=output.get("duration_ms"),
                    output_preview=str(output.get("output_preview") or ""),
                    error=output.get("error"),
                    outcome=output.get("outcome"),
                    artifacts=artifacts,
                    debug=debug,
                    provider_session=provider_session if isinstance(provider_session, Mapping) else {},
                    file_refs=self._step_file_refs(
                        name,
                        step_id=self._str_or_none(entry.get("step_id")),
                        visit_count=visit_count,
                        artifacts=artifacts,
                        debug=debug,
                        provider_session=provider_session if isinstance(provider_session, Mapping) else {},
                        resolver=resolver,
                        warnings=warnings,
                    ),
                )
            )
        return steps

    def _steps_from_state(
        self,
        state: Mapping[str, Any],
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> list[DashboardStep]:
        raw_steps = state.get("steps")
        if not isinstance(raw_steps, Mapping):
            return []
        steps: list[DashboardStep] = []
        for name, result in raw_steps.items():
            payload = result if isinstance(result, Mapping) else {}
            artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), Mapping) else {}
            debug = payload.get("debug") if isinstance(payload.get("debug"), Mapping) else {}
            provider_session = (
                debug.get("provider_session")
                if isinstance(debug.get("provider_session"), Mapping)
                else {}
            )
            steps.append(
                DashboardStep(
                    ref=self._step_ref(str(name), payload.get("step_id")),
                    name=str(name),
                    step_id=self._str_or_none(payload.get("step_id")),
                    status=str(payload.get("status") or "unknown"),
                    duration_ms=payload.get("duration_ms"),
                    visit_count=payload.get("visit_count"),
                    output_preview=self._output_preview(payload),
                    error=payload.get("error"),
                    outcome=payload.get("outcome"),
                    artifacts=artifacts,
                    debug=debug,
                    provider_session=provider_session,
                    file_refs=self._step_file_refs(
                        str(name),
                        step_id=self._str_or_none(payload.get("step_id")),
                        visit_count=payload.get("visit_count"),
                        artifacts=artifacts,
                        debug=debug,
                        provider_session=provider_session,
                        resolver=resolver,
                        warnings=warnings,
                    ),
                )
            )
        return steps

    def _step_file_refs(
        self,
        step_name: str,
        *,
        step_id: Optional[str],
        visit_count: Any,
        artifacts: Mapping[str, Any],
        debug: Mapping[str, Any],
        provider_session: Mapping[str, Any],
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> dict[str, FileReference]:
        refs = self._artifact_file_refs(artifacts, resolver, warnings)
        self._add_existing_run_ref(
            refs,
            "prompt_audit",
            f"logs/{step_name}.prompt.txt",
            "masked debug prompt file",
            resolver,
            warnings,
        )
        self._add_existing_run_ref(
            refs,
            "stdout_log",
            f"logs/{step_name}.stdout",
            "less-masked execution log",
            resolver,
            warnings,
        )
        self._add_existing_run_ref(
            refs,
            "stderr_log",
            f"logs/{step_name}.stderr",
            "less-masked execution log",
            resolver,
            warnings,
        )

        metadata_path = provider_session.get("metadata_path")
        if isinstance(metadata_path, str) and metadata_path:
            self._add_ref_from_any(
                refs,
                "provider_session_metadata",
                metadata_path,
                "provider-session metadata",
                resolver,
                warnings,
            )
        transport_path = provider_session.get("transport_spool_path")
        if isinstance(transport_path, str) and transport_path:
            self._add_ref_from_any(
                refs,
                "provider_transport_log",
                transport_path,
                "provider transport log",
                resolver,
                warnings,
            )

        if step_id and isinstance(visit_count, int):
            visit_key = f"{step_id.replace('/', '_')}__v{visit_count}"
            self._add_existing_run_ref(
                refs,
                "provider_session_metadata",
                f"provider_sessions/{visit_key}.json",
                "provider-session metadata",
                resolver,
                warnings,
            )
            self._add_existing_run_ref(
                refs,
                "provider_transport_log",
                f"provider_sessions/{visit_key}.transport.log",
                "provider transport log",
                resolver,
                warnings,
            )
        if isinstance(debug.get("provider_session"), Mapping) and not provider_session:
            warnings.append(f"provider session debug for {step_name} was not linkable")
        return refs

    def _artifact_file_refs(
        self,
        artifacts: Mapping[str, Any],
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> dict[str, FileReference]:
        refs: dict[str, FileReference] = {}
        for name, value in artifacts.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            try:
                refs[name] = resolver.from_any(value, label=name)
            except UnsafePathError as exc:
                warnings.append(f"unsafe artifact {name}: {exc}")
        return refs

    def _add_existing_run_ref(
        self,
        refs: dict[str, FileReference],
        name: str,
        route_path: str,
        label: str,
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> None:
        if name in refs:
            return
        try:
            file_ref = resolver.run_ref(route_path, label=label)
        except UnsafePathError as exc:
            warnings.append(f"unsafe run-local file {route_path}: {exc}")
            return
        if file_ref.status == "ok":
            refs[name] = file_ref

    def _add_ref_from_any(
        self,
        refs: dict[str, FileReference],
        name: str,
        value: str,
        label: str,
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> None:
        if name in refs:
            return
        try:
            file_ref = resolver.from_any(value, label=label)
        except UnsafePathError as exc:
            warnings.append(f"unsafe run-local file {value}: {exc}")
            return
        if file_ref.status == "ok":
            refs[name] = file_ref

    def _artifact_versions(
        self,
        state: Mapping[str, Any],
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        versions = state.get("artifact_versions")
        if not isinstance(versions, Mapping):
            return {}
        projected: dict[str, list[dict[str, Any]]] = {}
        for artifact_name, entries in versions.items():
            if not isinstance(artifact_name, str) or not isinstance(entries, list):
                continue
            projected_entries: list[dict[str, Any]] = []
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                copy_entry = dict(entry)
                value = copy_entry.get("value")
                if isinstance(value, str):
                    try:
                        copy_entry["file_ref"] = resolver.from_any(value, label=artifact_name)
                    except UnsafePathError as exc:
                        warnings.append(f"unsafe artifact {artifact_name}: {exc}")
                projected_entries.append(copy_entry)
            projected[artifact_name] = projected_entries
        return projected

    def _failure_summary(
        self,
        state: Mapping[str, Any],
        steps: list[DashboardStep],
        fallback: Optional[str],
    ) -> str:
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
        return fallback or ""

    def _availability(self, run_root: Path) -> dict[str, bool]:
        return {
            "prompt_audits": self._has_run_file(run_root, "logs/*.prompt.txt"),
            "stdout": self._has_run_file(run_root, "logs/*.stdout"),
            "stderr": self._has_run_file(run_root, "logs/*.stderr"),
            "provider_sessions": self._has_run_file(run_root, "provider_sessions/*"),
            "state_backups": self._has_run_file(run_root, "state.json.*.bak"),
        }

    def _observability_files(
        self,
        run_root: Path,
        resolver: FileReferenceResolver,
        warnings: list[str],
    ) -> dict[str, list[FileReference]]:
        groups = {
            "prompt_audits": ("logs/*.prompt.txt", "masked debug prompt file"),
            "stdout": ("logs/*.stdout", "less-masked execution log"),
            "stderr": ("logs/*.stderr", "less-masked execution log"),
            "provider_sessions": ("provider_sessions/*.json", "provider-session metadata"),
            "provider_transport": ("provider_sessions/*.transport.log", "provider transport log"),
            "state_backups": ("state.json.*.bak", "state backup"),
        }
        projected: dict[str, list[FileReference]] = {}
        for group, (pattern, label) in groups.items():
            refs: list[FileReference] = []
            for path in self._iter_run_files(run_root, pattern):
                try:
                    route_path = path.relative_to(run_root).as_posix()
                    file_ref = resolver.run_ref(route_path, label=label)
                except (OSError, UnsafePathError, ValueError) as exc:
                    warnings.append(f"unsafe run-local file {path}: {exc}")
                    continue
                if file_ref.status == "ok":
                    refs.append(file_ref)
            projected[group] = refs
        return projected

    def _common_artifact_refs(
        self,
        steps: list[DashboardStep],
        artifact_versions: Mapping[str, Any],
    ) -> dict[str, FileReference]:
        refs: dict[str, FileReference] = {}
        for step in steps:
            for artifact_name in step.artifacts:
                file_ref = step.file_refs.get(str(artifact_name))
                if file_ref is None:
                    continue
                key = str(artifact_name)
                if key in refs:
                    key = f"{step.name}.{artifact_name}"
                refs[key] = file_ref
        for artifact_name, entries in artifact_versions.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                file_ref = entry.get("file_ref")
                if not isinstance(file_ref, FileReference):
                    continue
                version = entry.get("version")
                key = str(artifact_name)
                if key in refs:
                    key = f"{artifact_name}@{version}" if version is not None else f"{artifact_name}.lineage"
                refs[key] = file_ref
        return refs

    def _has_run_file(self, run_root: Path, pattern: str) -> bool:
        return any(self._iter_run_files(run_root, pattern))

    def _iter_run_files(self, run_root: Path, pattern: str) -> list[Path]:
        try:
            return sorted(path for path in run_root.rglob(pattern) if path.is_file())
        except OSError:
            return []

    def _row(
        self,
        run: RunRecord,
        *,
        read_time: str,
        persisted_status: str,
        display_status: str,
        failure_summary: str = "",
        display_status_reason: Optional[str] = None,
        cursor_summary: str = "",
        workflow_file: Optional[str] = None,
        workflow_name: Optional[str] = None,
        warnings: Optional[list[str]] = None,
        availability: Optional[Mapping[str, bool]] = None,
    ) -> DashboardIndexRow:
        try:
            state_mtime = run.state_path.stat().st_mtime
        except OSError:
            state_mtime = None
        state = run.state if isinstance(run.state, Mapping) else {}
        heartbeat_at = self._heartbeat_at(state)
        heartbeat_age_seconds = self._heartbeat_age_seconds(heartbeat_at)
        return DashboardIndexRow(
            workspace_id=run.workspace.id,
            workspace_label=run.workspace.label,
            workspace_root=run.workspace.root,
            run_dir_id=run.run_dir_id,
            run_root=run.run_root,
            state_path=run.state_path,
            state_run_id=run.state_run_id,
            workflow_file=workflow_file,
            workflow_name=workflow_name,
            persisted_status=persisted_status,
            display_status=display_status,
            display_status_reason=display_status_reason,
            cursor_summary=cursor_summary,
            started_at=state.get("started_at"),
            updated_at=state.get("updated_at"),
            state_mtime=state_mtime,
            read_time=read_time,
            heartbeat_at=heartbeat_at,
            heartbeat_age_seconds=heartbeat_age_seconds,
            failure_summary=failure_summary,
            warnings=list(warnings or []),
            availability=dict(availability or {}),
        )

    def _output_preview(self, payload: Mapping[str, Any]) -> str:
        for key in ("text", "output"):
            value = payload.get(key)
            if isinstance(value, str):
                return value[:200]
        lines = payload.get("lines")
        if isinstance(lines, list):
            return "\n".join(str(line) for line in lines)[:200]
        json_payload = payload.get("json")
        if json_payload is not None:
            return str(json_payload)[:200]
        return ""

    def _step_ref(self, name: str, step_id: Any) -> str:
        value = step_id if isinstance(step_id, str) and step_id else name
        return str(value)

    def _heartbeat_at(self, state: Mapping[str, Any]) -> Optional[str]:
        current_step = state.get("current_step")
        if not isinstance(current_step, Mapping):
            return None
        heartbeat = current_step.get("last_heartbeat_at") or current_step.get("started_at")
        return heartbeat if isinstance(heartbeat, str) and heartbeat else None

    def _heartbeat_age_seconds(self, heartbeat_at: Optional[str]) -> Optional[float]:
        if heartbeat_at is None:
            return None
        parsed = self._parse_datetime(heartbeat_at)
        if parsed is None:
            return None
        return max(0.0, (self.now - parsed).total_seconds())

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _first_present(self, *values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    def _str_or_none(self, value: Any) -> Optional[str]:
        return value if isinstance(value, str) and value else None
