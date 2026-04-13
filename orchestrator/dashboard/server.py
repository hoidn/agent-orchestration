"""Stdlib HTTP server for the local read-only workflow dashboard."""

from __future__ import annotations

import html
import json
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
            "<thead><tr><th>Workspace</th><th>Run</th><th>State Run ID</th><th>Workflow</th><th>Persisted</th><th>Display</th><th>Cursor</th><th>Started</th><th>Updated</th><th>State mtime</th><th>Read time</th><th>Heartbeat</th><th>Availability</th><th>Failure</th></tr></thead>",
            "<tbody>",
        ])
        if not rows:
            lines.append("<tr><td colspan=\"14\">No runs matched.</td></tr>")
        for row in rows:
            detail_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            workflow = row.workflow_name or row.workflow_file or ""
            display = row.display_status
            if row.display_status_reason:
                display = f"{display} ({row.display_status_reason})"
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
                f"<td>{self._e(row.updated_at or '')}</td>"
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
        return filtered

    def _html_response(self, body: str, *, status: int = 200) -> DashboardResponse:
        return DashboardResponse(
            status=status,
            body=body.encode("utf-8"),
            headers=self._html_headers(),
        )

    def _response(self, status: int, text: str) -> DashboardResponse:
        return self._html_response(
            f"<!doctype html><html><body><h1>{self._e(text)}</h1></body></html>",
            status=status,
        )

    def _html_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "text/html; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": DASHBOARD_CSP,
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
