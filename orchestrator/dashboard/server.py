"""Stdlib HTTP server for the local read-only workflow dashboard."""

from __future__ import annotations

import html
import json
import secrets
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping, Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

from orchestrator.dashboard.commands import CommandBuilder
from orchestrator.dashboard.files import FileReferenceResolver, UnsafePathError
from orchestrator.dashboard.preview import DASHBOARD_CSP
from orchestrator.dashboard.preview import PreviewRenderer
from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner


@dataclass(frozen=True)
class DashboardResponse:
    """Testable dashboard response object."""

    status: int
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)


class DashboardApp:
    """Explicit route dispatcher for dashboard pages."""

    def __init__(
        self,
        scanner: RunScanner,
        *,
        now: str | datetime | Callable[[], str | datetime] | None = None,
    ) -> None:
        self.scanner = scanner
        self._now_provider = self._coerce_now_provider(now)

    def handle(self, method: str, target: str) -> DashboardResponse:
        request_now = self._now()
        if method != "GET":
            return self._response(405, "Method not allowed")
        parsed = urlsplit(target)
        if parsed.path == "/":
            return DashboardResponse(status=302, headers={"Location": "/runs"})
        if parsed.path == "/runs":
            query = parse_qs(parsed.query)
            return self._runs_index(query, request_now)
        segments = [unquote(segment) for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) >= 3 and segments[0] == "runs":
            workspace_id, run_dir_id = segments[1], segments[2]
            detail = self._find_detail(workspace_id, run_dir_id, request_now)
            if detail is None:
                return self._response(404, "Run not found")
            if len(segments) == 3:
                return self._run_detail(detail, refresh=self._refresh_seconds(parse_qs(parsed.query)))
            if len(segments) == 5 and segments[3] == "summaries" and segments[4] == "live.json":
                return self._summary_live_json(detail)
            if len(segments) == 4 and segments[3] == "summaries":
                return self._summary_hub(detail)
            if len(segments) == 4 and segments[3] == "state":
                return self._state_preview(detail)
            if len(segments) >= 5 and segments[3] == "steps":
                return self._step_detail(detail, "/".join(segments[4:]))
            if len(segments) >= 6 and segments[3] == "files":
                query = parse_qs(parsed.query)
                return self._file_route(
                    detail,
                    scope=segments[4],
                    route_path="/".join(segments[5:]),
                    raw=self._first(query, "raw") == "1",
                )
        return self._response(404, "Not found")

    def _runs_index(self, query: Mapping[str, list[str]], now: datetime) -> DashboardResponse:
        scan = self.scanner.scan()
        projector = RunProjector(now=now)
        rows = self._filter_rows(projector.project_index(scan.runs), query, now)
        refresh = self._refresh_seconds(query)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Workflow Runs</title>",
        ]
        if refresh is not None:
            lines.append(f"<meta http-equiv=\"refresh\" content=\"{refresh}\">")
        lines.extend([
            "<style>body{font-family:sans-serif;margin:2rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.35rem;text-align:left}code{white-space:pre-wrap}</style>",
            "</head><body>",
            "<main>",
            "<h1>Workflow Runs</h1>",
            '<p><a href="/runs">Refresh</a></p>',
            "<table>",
            "<thead><tr><th>Workspace</th><th>Run</th><th>State Run ID</th><th>Workflow</th><th>Persisted</th><th>Display</th><th>Cursor</th><th>Started</th><th>Elapsed</th><th>Updated</th><th>Current step start</th><th>State mtime</th><th>Read time</th><th>Heartbeat</th><th>Availability</th><th>Failure</th></tr></thead>",
            "<tbody>",
        ])
        if not rows:
            lines.append("<tr><td colspan=\"16\">No runs matched.</td></tr>")
        for row in rows:
            detail_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            workflow = row.workflow_name or row.workflow_file or ""
            display = row.display_status
            if row.display_status_reason:
                display = f"{display} ({row.display_status_reason})"
            elapsed = (
                self._format_duration(row.elapsed_seconds)
                if row.elapsed_seconds is not None
                else ""
            )
            current_step_started = row.current_step_started_at or ""
            if row.current_step_age_seconds is not None:
                current_step_started = (
                    f"{current_step_started} "
                    f"({self._format_duration(row.current_step_age_seconds)})"
                )
            heartbeat = row.heartbeat_at or ""
            if row.heartbeat_age_seconds is not None:
                heartbeat = f"{heartbeat} ({self._format_duration(row.heartbeat_age_seconds)})"
            lines.append(
                "<tr>"
                f"<td>{self._e(row.workspace_label)}<br><small>{self._e(str(row.workspace_root))}</small></td>"
                f"<td><a href=\"{detail_href}\">{self._e(row.run_dir_id)}</a></td>"
                f"<td>{self._e(row.state_run_id or '')}</td>"
                f"<td>{self._e(workflow)}</td>"
                f"<td>{self._e(row.persisted_status)}</td>"
                f"<td>{self._e(display)}</td>"
                f"<td>{self._e(row.cursor_summary)}</td>"
                f"<td>{self._e(row.started_at or '')}</td>"
                f"<td>{self._e(elapsed)}</td>"
                f"<td>{self._e(row.updated_at or '')}</td>"
                f"<td>{self._e(current_step_started)}</td>"
                f"<td>{self._e(self._format_timestamp(row.state_mtime))}</td>"
                f"<td>{self._e(row.read_time or '')}</td>"
                f"<td>{self._e(heartbeat)}</td>"
                f"<td>{self._e(self._format_availability(row.availability))}</td>"
                f"<td>{self._e(row.failure_summary)}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</main>", "</body></html>"])
        return self._html_response("\n".join(lines))

    def _find_detail(self, workspace_id: str, run_dir_id: str, now: datetime):
        scan = self.scanner.scan()
        for run in scan.runs:
            if run.workspace.id == workspace_id and run.run_dir_id == run_dir_id:
                return RunProjector(now=now).project_detail(run)
        return None

    def _run_detail(self, detail, *, refresh: Optional[int] = None) -> DashboardResponse:
        row = detail.row
        commands = CommandBuilder().build(self._run_record_for_detail(detail))
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Run Detail</title>",
        ]
        if refresh is not None:
            lines.append(f"<meta http-equiv=\"refresh\" content=\"{refresh}\">")
        lines.extend([
            "<style>body{font-family:sans-serif;margin:2rem}section{margin-block:1.5rem}pre{background:#f5f5f5;padding:.75rem;overflow:auto}li{margin:.25rem 0}</style>",
            "</head><body><main>",
            f"<h1>Run {self._e(row.run_dir_id)}</h1>",
            "<section><h2>Summary</h2>",
            "<dl>",
            f"<dt>Workspace</dt><dd>{self._e(str(row.workspace_root))}</dd>",
            f"<dt>State run id</dt><dd>{self._e(row.state_run_id or '')}</dd>",
            f"<dt>Workflow</dt><dd>{self._e(row.workflow_name or row.workflow_file or '')}</dd>",
            f"<dt>Persisted status</dt><dd>{self._e(row.persisted_status)}</dd>",
            f"<dt>Display status</dt><dd>{self._e(row.display_status)} {self._e(row.display_status_reason or '')}</dd>",
            "</dl>",
            "</section>",
        ])
        all_warnings = list(detail.warnings) + list(commands.warnings)
        if all_warnings:
            lines.extend(["<section><h2>Warnings</h2><ul>"])
            for warning in all_warnings:
                lines.append(f"<li>{self._e(warning)}</li>")
            lines.append("</ul></section>")

        lines.extend(["<section><h2>Commands</h2>"])
        if commands.report is None and commands.resume is None and not commands.tmux:
            lines.append("<p>Commands unavailable for this run.</p>")
        if commands.report is not None:
            lines.append(f"<p>cwd: <code>{self._e(str(commands.report.cwd))}</code></p>")
            lines.append(f"<pre>{self._e(commands.report.shell_text)}</pre>")
        if commands.resume is not None:
            lines.append(f"<pre>{self._e(commands.resume.shell_text)}</pre>")
        lines.append("</section>")

        if detail.cursor is not None:
            lines.extend(["<section><h2>Active Cursor</h2><ul>"])
            for node in detail.cursor.nodes:
                lines.append(
                    f"<li>{self._e(node.kind)}: {self._e(node.name)} "
                    f"<pre>{self._json(node.details)}</pre></li>"
                )
            lines.append("</ul></section>")

        lines.extend(["<section><h2>Summary Hub</h2>"])
        summary_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/summaries"
        if (row.run_root / "summaries" / "index.json").exists():
            lines.append(f"<p><a href=\"{summary_href}\">Open Summary Hub</a></p>")
        else:
            lines.append("<p>No summary hub is available for this run.</p>")
        lines.append("</section>")

        lines.extend(["<section><h2>Step Timeline</h2><ul>"])
        for step in detail.steps:
            href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/steps/{quote(step.ref)}"
            lines.append(
                f"<li><a href=\"{href}\">{self._e(step.name)}</a> "
                f"{self._e(step.status)} {self._e(step.kind)}</li>"
            )
            if step.file_refs:
                lines.append("<ul>")
                for name, file_ref in step.file_refs.items():
                    lines.append(
                        f"<li>{self._e(name)} ({self._e(file_ref.label or '')}): "
                        f"<a href=\"{self._file_href(row, file_ref)}\">"
                        f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
                    )
                lines.append("</ul>")
        lines.append("</ul></section>")

        lines.extend(["<section><h2>Observability Files</h2>"])
        self._append_file_group(
            lines,
            row,
            "Prompt Audits",
            detail.observability_files.get("prompt_audits", []),
        )
        self._append_file_group(
            lines,
            row,
            "Execution Logs",
            list(detail.observability_files.get("stdout", []))
            + list(detail.observability_files.get("stderr", [])),
        )
        self._append_file_group(
            lines,
            row,
            "Provider Sessions",
            list(detail.observability_files.get("provider_sessions", []))
            + list(detail.observability_files.get("provider_transport", [])),
        )
        self._append_file_group(
            lines,
            row,
            "State Backups",
            detail.observability_files.get("state_backups", []),
        )
        self._append_file_group(
            lines,
            row,
            "Summary Hub Files",
            detail.observability_files.get("summaries", []),
        )
        lines.append("</section>")

        lines.extend(["<section><h2>Common Artifacts</h2>"])
        if detail.common_artifact_refs:
            lines.append("<ul>")
            for name, file_ref in detail.common_artifact_refs.items():
                lines.append(
                    f"<li>{self._e(name)}: <a href=\"{self._file_href(row, file_ref)}\">"
                    f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
                )
            lines.append("</ul>")
        else:
            lines.append("<p>No common artifact file references.</p>")
        lines.append("</section>")

        lines.append("<section><h2>Inputs</h2>")
        lines.append(f"<pre>{self._json(detail.bound_inputs)}</pre></section>")
        lines.append("<section><h2>Outputs</h2>")
        lines.append(f"<pre>{self._json(detail.workflow_outputs)}</pre></section>")
        lines.append("<section><h2>Run Error</h2>")
        lines.append(f"<pre>{self._json(detail.error)}</pre></section>")
        lines.append("<section><h2>Finalization</h2>")
        lines.append(f"<pre>{self._json(detail.finalization)}</pre></section>")
        lines.append("<section><h2>artifact_versions</h2>")
        lines.append(f"<pre>{self._json(detail.artifact_versions)}</pre></section>")
        lines.append("<section><h2>artifact_consumes</h2>")
        lines.append(f"<pre>{self._json(detail.artifact_consumes)}</pre></section>")
        lines.append("<section><h2>call_frame_artifact_versions</h2>")
        lines.append(f"<pre>{self._json(detail.call_frame_artifact_versions)}</pre></section>")
        lines.append("<section><h2>call_frame_artifact_consumes</h2>")
        lines.append(f"<pre>{self._json(detail.call_frame_artifact_consumes)}</pre></section>")
        lines.append(f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/state\">State JSON</a></p>")
        lines.extend(["</main></body></html>"])
        return self._html_response("\n".join(lines))

    def _summary_hub(self, detail) -> DashboardResponse:
        row = detail.row
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        back_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
        live_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/summaries/live.json"
        script_nonce = secrets.token_urlsafe(16)
        index_path = row.run_root / "summaries" / "index.json"
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Summary Hub</title>",
            "<style>body{font-family:sans-serif;margin:2rem}section{margin-block:1.5rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.35rem;text-align:left;vertical-align:top}pre{background:#f5f5f5;padding:.75rem;overflow:auto}code{white-space:pre-wrap}.muted{color:#555}.live-panel{border:1px solid #bbb;border-radius:6px;padding:1rem;background:#fafafa}.live-grid{display:grid;grid-template-columns:max-content 1fr;gap:.35rem .75rem}.live-grid dt{font-weight:600}.live-grid dd{margin:0}</style>",
            "</head><body><main>",
            f"<h1>Summary Hub: {self._e(row.run_dir_id)}</h1>",
            f"<p><a href=\"{back_href}\">Back to run</a></p>",
            f"<section id=\"live-current-step\" class=\"live-panel\" data-live-url=\"{live_href}\">",
            "<h2>Current Step</h2>",
            "<dl class=\"live-grid\">",
            "<dt>Run</dt><dd><span data-live-field=\"run-status\">Loading...</span></dd>",
            "<dt>Step</dt><dd><span data-live-field=\"step-name\">Loading...</span></dd>",
            "<dt>Started</dt><dd><span data-live-field=\"step-started\"></span></dd>",
            "<dt>Age</dt><dd><span data-live-field=\"step-age\"></span></dd>",
            "<dt>Heartbeat</dt><dd><span data-live-field=\"heartbeat\"></span></dd>",
            "<dt>Summaries</dt><dd><span data-live-field=\"summary-counts\"></span></dd>",
            "<dt>Latest current-step summary</dt><dd><a data-live-link=\"latest-summary\" hidden>Open summary</a><span data-live-field=\"latest-summary-empty\">None yet.</span></dd>",
            "<dt>Live agent note</dt><dd><pre data-live-field=\"live-note\">No live note yet.</pre><a data-live-link=\"live-note\" hidden>Open live note</a></dd>",
            "</dl>",
            "<p class=\"muted\">Updates every few seconds from run state and summary artifacts.</p>",
            "</section>",
        ]
        if not index_path.exists():
            lines.extend(
                [
                    "<section><h2>No Summary Hub</h2>",
                    "<p>No summary hub is available for this run.</p>",
                    "</section></main></body></html>",
                ]
            )
            return self._html_response("\n".join(lines), script_nonce=script_nonce)

        try:
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            index_ref = resolver.run_ref("summaries/index.json", label="summary index")
            lines.extend(
                [
                    "<section><h2>Summary index is invalid</h2>",
                    f"<p>{self._e(exc)}</p>",
                    f"<p><a href=\"{self._file_href(row, index_ref)}\">View index file</a></p>",
                    "</section></main></body></html>",
                ]
            )
            return self._html_response("\n".join(lines), script_nonce=script_nonce)

        entries = index_payload.get("entries") if isinstance(index_payload, Mapping) else None
        if not isinstance(entries, list):
            entries = []
            warning = "Summary index is invalid: entries must be a list."
        else:
            warning = ""
        counts: dict[str, int] = {}
        for entry in entries:
            if isinstance(entry, Mapping):
                kind = str(entry.get("kind") or "step")
                counts[kind] = counts.get(kind, 0) + 1
        counts_text = ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())) or "none"
        lines.extend(
            [
                "<section><h2>Overview</h2>",
                f"<p>Total summaries: {self._e(len(entries))}; {self._e(counts_text)}</p>",
            ]
        )
        if warning:
            lines.append(f"<p>{self._e(warning)}</p>")
        lines.append("</section>")

        lines.extend(
            [
                "<section><h2>Summary Entries</h2>",
                "<table>",
                "<thead><tr><th>Step</th><th>Kind</th><th>Profile</th><th>Status</th><th>Duration</th><th>Frame</th><th>Files</th></tr></thead>",
                "<tbody>",
            ]
        )
        if not entries:
            lines.append("<tr><td colspan=\"7\">No summary entries.</td></tr>")
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            duration = entry.get("duration_ms")
            duration_text = f"{duration} ms" if duration is not None else ""
            file_links = self._summary_entry_links(row, resolver, entry)
            lines.append(
                "<tr>"
                f"<td>{self._e(entry.get('step_name') or '')}</td>"
                f"<td>{self._e(entry.get('kind') or '')}</td>"
                f"<td>{self._e(entry.get('profile') or '')}</td>"
                f"<td>{self._e(entry.get('status') or '')}</td>"
                f"<td>{self._e(duration_text)}</td>"
                f"<td>{self._e(entry.get('frame_root') or '')}</td>"
                f"<td>{file_links}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</section>"])

        lines.extend(["<section><h2>Run Summary Preview</h2>"])
        try:
            summary_ref = resolver.run_ref("summaries/run-summary.md", label="run summary")
        except UnsafePathError:
            summary_ref = None
        if summary_ref is not None and summary_ref.status == "ok":
            preview = PreviewRenderer().preview(summary_ref.absolute_path)
            if preview.status == "ok":
                if preview.truncated:
                    size = preview.size_bytes if preview.size_bytes is not None else ""
                    lines.append(
                        f"<p>Preview truncated at dashboard cap; file size {self._e(size)} bytes.</p>"
                    )
                lines.append(f"<pre>{preview.display_text}</pre>")
            else:
                lines.append(f"<p>{self._e(preview.status)}</p>")
            lines.append(f"<p><a href=\"{self._file_href(row, summary_ref)}\">Open run-summary.md</a></p>")
        else:
            lines.append("<p>No run-summary.md file is available.</p>")
        lines.extend([
            "</section>",
            self._summary_live_script(script_nonce),
            "</main></body></html>",
        ])
        return self._html_response("\n".join(lines), script_nonce=script_nonce)

    def _summary_live_json(self, detail) -> DashboardResponse:
        return self._json_response(self._summary_live_payload(detail))

    def _summary_live_payload(self, detail) -> dict[str, object]:
        row = detail.row
        resolver = FileReferenceResolver(row.workspace_root, row.run_root)
        state = detail.state if isinstance(detail.state, Mapping) else {}
        current_step = state.get("current_step") if isinstance(state.get("current_step"), Mapping) else {}
        current_name = self._str_or_none(current_step.get("name"))
        current_step_id = self._str_or_none(current_step.get("step_id"))
        entries = self._summary_index_entries(row.run_root)
        counts: dict[str, int] = {}
        for entry in entries:
            kind = str(entry.get("kind") or "step")
            counts[kind] = counts.get(kind, 0) + 1

        latest = None
        if current_name:
            for entry in reversed(entries):
                if str(entry.get("step_name") or "") == current_name:
                    latest = self._summary_entry_payload(row, resolver, entry)
                    break

        step_href = None
        if current_name or current_step_id:
            for step in detail.steps:
                if current_name in {step.name, step.ref} or current_step_id in {step.step_id, step.ref}:
                    step_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}/steps/{quote(step.ref)}"
                    break

        return {
            "schema": "dashboard_summary_live/v1",
            "run": {
                "run_dir_id": row.run_dir_id,
                "state_run_id": row.state_run_id,
                "persisted_status": row.persisted_status,
                "display_status": row.display_status,
                "display_status_reason": row.display_status_reason,
                "cursor_summary": row.cursor_summary,
                "read_time": row.read_time,
            },
            "current_step": {
                "name": current_name,
                "step_id": current_step_id,
                "started_at": self._str_or_none(current_step.get("started_at")),
                "age_seconds": row.current_step_age_seconds,
                "age_text": (
                    self._format_duration(row.current_step_age_seconds)
                    if row.current_step_age_seconds is not None
                    else ""
                ),
                "heartbeat_at": row.heartbeat_at,
                "heartbeat_age_seconds": row.heartbeat_age_seconds,
                "heartbeat_age_text": (
                    self._format_duration(row.heartbeat_age_seconds)
                    if row.heartbeat_age_seconds is not None
                    else ""
                ),
                "step_href": step_href,
            },
            "summaries": {
                "total": len(entries),
                "counts": counts,
                "current_step_latest": latest,
            },
            "live_note": self._live_agent_note_payload(row, resolver, current_name, current_step_id),
        }

    def _live_agent_note_payload(
        self,
        row,
        resolver: FileReferenceResolver,
        current_name: Optional[str],
        current_step_id: Optional[str],
    ) -> dict[str, object] | None:
        try:
            metadata_ref = resolver.run_ref("summaries/live-current-step.json", label="live note metadata")
            note_ref = resolver.run_ref("summaries/live-current-step.md", label="live note")
        except UnsafePathError:
            return None
        if metadata_ref.status != "ok" or note_ref.status != "ok":
            return None
        try:
            metadata = json.loads(metadata_ref.absolute_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(metadata, Mapping):
            return None
        note_step_name = self._str_or_none(metadata.get("step_name"))
        note_step_id = self._str_or_none(metadata.get("step_id"))
        if current_name and note_step_name and note_step_name != current_name:
            return None
        if current_step_id and note_step_id and note_step_id != current_step_id:
            return None
        try:
            text = note_ref.absolute_path.read_text(encoding="utf-8")[:4000]
        except OSError:
            text = ""
        return {
            "text": text,
            "step_name": note_step_name,
            "step_id": note_step_id,
            "visit_count": metadata.get("visit_count"),
            "provider": self._str_or_none(metadata.get("provider")),
            "generated_at": self._str_or_none(metadata.get("generated_at")),
            "summary_href": self._file_href(row, note_ref),
            "metadata_href": self._file_href(row, metadata_ref),
        }

    def _summary_index_entries(self, run_root) -> list[Mapping[str, object]]:
        index_path = run_root / "summaries" / "index.json"
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries = payload.get("entries") if isinstance(payload, Mapping) else None
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, Mapping)]

    def _summary_entry_payload(self, row, resolver: FileReferenceResolver, entry: Mapping[str, object]) -> dict[str, object]:
        payload: dict[str, object] = {
            "step_name": str(entry.get("step_name") or ""),
            "kind": str(entry.get("kind") or ""),
            "profile": str(entry.get("profile") or ""),
            "status": str(entry.get("status") or ""),
            "duration_ms": entry.get("duration_ms"),
            "frame_root": str(entry.get("frame_root") or ""),
        }
        for key, output_key in (
            ("summary_path", "summary_href"),
            ("snapshot_path", "snapshot_href"),
            ("error_path", "error_href"),
        ):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                payload[output_key] = None
                continue
            try:
                file_ref = resolver.run_ref(value)
            except UnsafePathError:
                payload[output_key] = None
                continue
            payload[output_key] = self._file_href(row, file_ref)
        return payload

    def _summary_live_script(self, nonce: str) -> str:
        return (
            f"<script nonce=\"{self._e(nonce)}\">\n"
            "(() => {\n"
            "  const root = document.getElementById('live-current-step');\n"
            "  if (!root || !root.dataset.liveUrl) return;\n"
            "  const text = (name, value) => {\n"
            "    const el = root.querySelector(`[data-live-field=\"${name}\"]`);\n"
            "    if (el) el.textContent = value || '';\n"
            "  };\n"
            "  const refresh = async () => {\n"
            "    let data;\n"
            "    try {\n"
            "      const response = await fetch(root.dataset.liveUrl, {cache: 'no-store'});\n"
            "      if (!response.ok) return;\n"
            "      data = await response.json();\n"
            "    } catch (_error) { return; }\n"
            "    const run = data.run || {};\n"
            "    const step = data.current_step || {};\n"
            "    const summaries = data.summaries || {};\n"
            "    text('run-status', [run.display_status, run.display_status_reason].filter(Boolean).join(' '));\n"
            "    text('step-name', step.name || 'No current step');\n"
            "    text('step-started', step.started_at || '');\n"
            "    text('step-age', step.age_text || '');\n"
            "    text('heartbeat', [step.heartbeat_at, step.heartbeat_age_text].filter(Boolean).join(' '));\n"
            "    const counts = summaries.counts || {};\n"
            "    const countText = Object.keys(counts).sort().map((key) => `${key}=${counts[key]}`).join(', ');\n"
            "    text('summary-counts', `${summaries.total || 0}${countText ? ` (${countText})` : ''}`);\n"
            "    const latest = summaries.current_step_latest || {};\n"
            "    const liveNote = data.live_note || {};\n"
            "    const link = root.querySelector('[data-live-link=\"latest-summary\"]');\n"
            "    const empty = root.querySelector('[data-live-field=\"latest-summary-empty\"]');\n"
            "    if (link && latest.summary_href) {\n"
            "      link.href = latest.summary_href;\n"
            "      link.textContent = [latest.kind, latest.status].filter(Boolean).join(' ') || 'Open summary';\n"
            "      link.hidden = false;\n"
            "      if (empty) empty.hidden = true;\n"
            "    } else {\n"
            "      if (link) link.hidden = true;\n"
            "      if (empty) empty.hidden = false;\n"
            "    }\n"
            "    text('live-note', liveNote.text || 'No live note yet.');\n"
            "    const liveLink = root.querySelector('[data-live-link=\"live-note\"]');\n"
            "    if (liveLink && liveNote.summary_href) {\n"
            "      liveLink.href = liveNote.summary_href;\n"
            "      liveLink.textContent = liveNote.generated_at ? `Open live note (${liveNote.generated_at})` : 'Open live note';\n"
            "      liveLink.hidden = false;\n"
            "    } else if (liveLink) {\n"
            "      liveLink.hidden = true;\n"
            "    }\n"
            "  };\n"
            "  refresh();\n"
            "  setInterval(refresh, 3000);\n"
            "})();\n"
            "</script>"
        )

    def _step_detail(self, detail, step_ref: str) -> DashboardResponse:
        row = detail.row
        step = next(
            (
                candidate
                for candidate in detail.steps
                if step_ref in {candidate.ref, candidate.name, candidate.step_id}
            ),
            None,
        )
        if step is None:
            return self._response(404, "Step not found")
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Step Detail</title></head><body><main>",
            f"<h1>{self._e(step.name)}</h1>",
            f"<p>Status: {self._e(step.status)}</p>",
            f"<p>Kind: {self._e(step.kind)}</p>",
            f"<p>Step id: {self._e(step.step_id or '')}</p>",
            f"<p>Visit count: {self._e(step.visit_count if step.visit_count is not None else '')}</p>",
            f"<p>Duration: {self._e(str(step.duration_ms) + ' ms' if step.duration_ms is not None else '')}</p>",
            "<h2>Output Preview</h2>",
            f"<pre>{self._e(step.output_preview)}</pre>",
            "<h2>Error</h2>",
            f"<pre>{self._json(step.error)}</pre>",
            "<h2>Outcome</h2>",
            f"<pre>{self._json(step.outcome)}</pre>",
            "<h2>Debug</h2>",
            f"<pre>{self._json(step.debug)}</pre>",
            "<h2>Provider Session</h2>",
            f"<pre>{self._json(step.provider_session)}</pre>",
            "<h2>Artifacts</h2>",
            f"<pre>{self._json(step.artifacts)}</pre>",
        ]
        if step.file_refs:
            lines.extend(["<h2>Files</h2>", "<ul>"])
            for name, file_ref in step.file_refs.items():
                lines.append(
                    f"<li>{self._e(name)} ({self._e(file_ref.label or '')}): "
                    f"<a href=\"{self._file_href(row, file_ref)}\">"
                    f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
                )
            lines.append("</ul>")
        lines.extend([
            f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}\">Back to run</a></p>",
            "</main></body></html>",
        ])
        return self._html_response("\n".join(lines))

    def _state_preview(self, detail) -> DashboardResponse:
        try:
            resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)
            file_ref = resolver.run_ref("state.json", label="state json")
        except UnsafePathError:
            return self._response(400, "Unsafe state path")
        if file_ref.status != "ok":
            body = (
                "<!doctype html><html><body><main>"
                f"<h1>{self._e(file_ref.status)}</h1>"
                "<p>state.json</p>"
                "</main></body></html>"
            )
            return self._html_response(body)

        preview = PreviewRenderer().preview(file_ref.absolute_path)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>State Preview</title></head><body><main>",
            f"<h1>State JSON for {self._e(detail.row.run_dir_id)}</h1>",
            f"<p>Status: {self._e(preview.status)}</p>",
        ]
        if preview.truncated:
            size = preview.size_bytes if preview.size_bytes is not None else ""
            lines.append(
                f"<p>Preview truncated at dashboard cap; file size {self._e(size)} bytes.</p>"
            )
        lines.extend([
            f"<pre>{preview.display_text}</pre>",
            "</main></body></html>",
        ])
        return DashboardResponse(
            status=200,
            body="\n".join(lines).encode("utf-8"),
            headers={**self._html_headers(), **dict(preview.headers)},
        )

    def _file_route(
        self,
        detail,
        *,
        scope: str,
        route_path: str,
        raw: bool,
    ) -> DashboardResponse:
        try:
            resolver = FileReferenceResolver(detail.row.workspace_root, detail.row.run_root)
            if scope == "workspace":
                file_ref = resolver.workspace_ref(route_path)
            elif scope == "run":
                file_ref = resolver.run_ref(route_path)
            else:
                return self._response(404, "Unknown file scope")
        except UnsafePathError:
            return self._response(400, "Unsafe path")

        renderer = PreviewRenderer()
        if raw:
            if file_ref.status != "ok":
                return self._response(404, file_ref.status)
            raw_result = renderer.raw(file_ref.absolute_path)
            return DashboardResponse(
                status=200 if raw_result.status == "ok" else 404,
                body=raw_result.body,
                headers=dict(raw_result.headers),
            )

        if file_ref.status != "ok":
            body = (
                "<!doctype html><html><body><main>"
                f"<h1>{self._e(file_ref.status)}</h1>"
                f"<p>{self._e(scope)}:{self._e(route_path)}</p>"
                "</main></body></html>"
            )
            return self._html_response(body)

        preview = renderer.preview(file_ref.absolute_path)
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>File Preview</title></head><body><main>",
            f"<h1>{self._e(scope)}:{self._e(file_ref.route_path)}</h1>",
            f"<p>Status: {self._e(preview.status)}</p>",
            f"<p><a href=\"{self._file_href(detail.row, file_ref)}?raw=1\">Download raw</a></p>",
        ]
        if preview.truncated:
            size = preview.size_bytes if preview.size_bytes is not None else ""
            lines.append(
                f"<p>Preview truncated at dashboard cap; file size {self._e(size)} bytes.</p>"
            )
        lines.extend([
            f"<pre>{preview.display_text}</pre>",
            "</main></body></html>",
        ])
        body = "\n".join(lines)
        return DashboardResponse(
            status=200,
            body=body.encode("utf-8"),
            headers={**self._html_headers(), **dict(preview.headers)},
        )

    def _file_href(self, row, file_ref) -> str:
        return (
            f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            f"/files/{quote(file_ref.scope)}/{quote(file_ref.route_path)}"
        )

    def _summary_entry_links(self, row, resolver: FileReferenceResolver, entry: Mapping[str, object]) -> str:
        links: list[str] = []
        for key, label in (
            ("summary_path", "summary"),
            ("snapshot_path", "snapshot"),
            ("error_path", "error"),
        ):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                continue
            try:
                file_ref = resolver.run_ref(value, label=label)
            except UnsafePathError:
                links.append(f"{self._e(label)}: <span class=\"muted\">unsafe path</span>")
                continue
            links.append(f"<a href=\"{self._file_href(row, file_ref)}\">{self._e(label)}</a>")
        return " ".join(links) if links else ""

    def _append_file_group(self, lines: list[str], row, title: str, refs) -> None:
        lines.append(f"<h3>{self._e(title)}</h3>")
        if not refs:
            lines.append("<p>None found.</p>")
            return
        lines.append("<ul>")
        for file_ref in refs:
            label = file_ref.label or file_ref.status
            lines.append(
                f"<li>{self._e(label)}: <a href=\"{self._file_href(row, file_ref)}\">"
                f"{self._e(file_ref.scope)}:{self._e(file_ref.route_path)}</a></li>"
            )
        lines.append("</ul>")

    def _run_record_for_detail(self, detail):
        scan = self.scanner.scan()
        for run in scan.runs:
            if (
                run.workspace.id == detail.row.workspace_id
                and run.run_dir_id == detail.row.run_dir_id
            ):
                return run
        raise LookupError("run disappeared during dashboard request")

    def _filter_rows(self, rows, query: Mapping[str, list[str]], now: datetime):
        workspace_filter = self._first(query, "workspace")
        status_filter = self._first(query, "status")
        workflow_filter = self._first(query, "workflow")
        search_filter = self._first(query, "search")
        recency_filter = self._parse_recency(self._first(query, "recency"))
        filtered = []
        for row in rows:
            if workspace_filter and workspace_filter not in {
                row.workspace_id,
                row.workspace_label,
                str(row.workspace_root),
            }:
                continue
            if status_filter and status_filter not in {
                row.persisted_status,
                row.display_status,
            }:
                continue
            if workflow_filter:
                haystack = f"{row.workflow_name or ''} {row.workflow_file or ''}".lower()
                if workflow_filter.lower() not in haystack:
                    continue
            if search_filter:
                haystack = " ".join(
                    [
                        row.run_dir_id,
                        row.state_run_id or "",
                        row.workflow_file or "",
                        row.workflow_name or "",
                        row.failure_summary or "",
                    ]
                ).lower()
                if search_filter.lower() not in haystack:
                    continue
            if recency_filter is not None:
                updated_at = self._parse_datetime(row.updated_at)
                if updated_at is None or now - updated_at > recency_filter:
                    continue
            filtered.append(row)
        filtered.sort(key=self._run_recency_sort_key)
        return filtered

    def _run_recency_sort_key(self, row) -> tuple[float, str, str, str]:
        return (
            -self._run_recency_timestamp(row),
            row.workspace_label,
            row.workspace_id,
            row.run_dir_id,
        )

    def _run_recency_timestamp(self, row) -> float:
        updated_at = self._parse_datetime(row.updated_at)
        if updated_at is not None:
            return updated_at.timestamp()
        if isinstance(row.state_mtime, (int, float)):
            return float(row.state_mtime)
        started_at = self._parse_datetime(row.started_at)
        if started_at is not None:
            return started_at.timestamp()
        return float("-inf")

    def _html_response(
        self,
        body: str,
        *,
        status: int = 200,
        script_nonce: Optional[str] = None,
    ) -> DashboardResponse:
        return DashboardResponse(
            status=status,
            body=body.encode("utf-8"),
            headers=self._html_headers(script_nonce=script_nonce),
        )

    def _json_response(self, payload: Mapping[str, object], *, status: int = 200) -> DashboardResponse:
        return DashboardResponse(
            status=status,
            body=(json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": DASHBOARD_CSP,
            },
        )

    def _response(self, status: int, text: str) -> DashboardResponse:
        return self._html_response(
            f"<!doctype html><html><body><h1>{self._e(text)}</h1></body></html>",
            status=status,
        )

    def _html_headers(self, *, script_nonce: Optional[str] = None) -> dict[str, str]:
        csp = DASHBOARD_CSP
        if script_nonce:
            csp = (
                "default-src 'none'; base-uri 'none'; object-src 'none'; "
                f"frame-ancestors 'none'; script-src 'nonce-{script_nonce}'; "
                "connect-src 'self'; style-src 'unsafe-inline'; img-src 'self' data:"
            )
        return {
            "Content-Type": "text/html; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": csp,
        }

    def _now(self) -> datetime:
        return self._now_provider()

    def _coerce_now_provider(
        self,
        value: str | datetime | Callable[[], str | datetime] | None,
    ) -> Callable[[], datetime]:
        if callable(value):
            return lambda: self._coerce_now_value(value())
        fixed = self._coerce_now_value(value) if value is not None else None
        if fixed is not None:
            return lambda: fixed
        return lambda: datetime.now(timezone.utc)

    def _coerce_now_value(self, value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            parsed = self._parse_datetime(value)
            if parsed is not None:
                return parsed
        return datetime.now(timezone.utc)

    def _parse_datetime(self, value: object) -> Optional[datetime]:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _parse_recency(self, value: Optional[str]) -> Optional[timedelta]:
        if not value:
            return None
        units = {"m": 60, "h": 3600, "d": 86400}
        try:
            if value[-1] in units:
                seconds = int(value[:-1]) * units[value[-1]]
            else:
                seconds = int(value)
        except (ValueError, IndexError):
            return None
        return timedelta(seconds=seconds)

    def _refresh_seconds(self, query: Mapping[str, list[str]]) -> Optional[int]:
        value = self._first(query, "refresh")
        if value is None:
            return None
        try:
            seconds = int(value)
        except ValueError:
            return None
        if seconds < 1 or seconds > 3600:
            return None
        return seconds

    def _first(self, query: Mapping[str, list[str]], key: str) -> Optional[str]:
        values = query.get(key)
        if not values:
            return None
        return unquote(values[0])

    def _str_or_none(self, value: object) -> Optional[str]:
        return value if isinstance(value, str) else None

    def _e(self, value: object) -> str:
        return html.escape(str(value), quote=True)

    def _format_availability(self, availability: Mapping[str, bool]) -> str:
        if not availability:
            return ""
        return ", ".join(
            f"{key}={'yes' if value else 'no'}"
            for key, value in sorted(availability.items())
        )

    def _format_timestamp(self, value: object) -> str:
        if not isinstance(value, (int, float)):
            return ""
        try:
            return datetime.fromtimestamp(value, timezone.utc).isoformat()
        except (OSError, ValueError):
            return str(value)

    def _format_duration(self, seconds_value: float) -> str:
        seconds = int(seconds_value)
        if seconds < 60:
            return f"{seconds}s"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"

    def _json(self, value: object) -> str:
        return html.escape(
            json.dumps(value, indent=2, default=self._json_default, sort_keys=True),
            quote=False,
        )

    def _json_default(self, value: object) -> object:
        if hasattr(value, "scope") and hasattr(value, "route_path"):
            return {
                "scope": getattr(value, "scope"),
                "route_path": getattr(value, "route_path"),
                "status": getattr(value, "status", None),
            }
        return str(value)


def serve_dashboard(*, scanner: RunScanner, host: str = "127.0.0.1", port: Optional[int] = None) -> int:
    """Serve the dashboard until interrupted."""
    bind_port = 8765 if port is None else port
    app = DashboardApp(scanner)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            response = app.handle("GET", self.path)
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            print(format % args, file=sys.stderr)

    server = ThreadingHTTPServer((host, bind_port), Handler)
    actual_host, actual_port = server.server_address
    print(f"Dashboard listening on http://{actual_host}:{actual_port}/runs")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
