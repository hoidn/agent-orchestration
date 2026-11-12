"""Stdlib HTTP server for the local read-only workflow dashboard.

Routes: `/runs`, `/runs/<workspace>/<run>` (run page), `.../steps/<effect>` (effect page), `.../state`
(derived `state.json` preview) and `.../files/<workspace|run>/<path>` (escaped preview or `?raw=1`
attachment). A retired run's routes below its run page return 404 with the refusal line. The run page
is rendered by `run_page`, the file and state pages by `file_pages`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping, Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

from orchestrator.dashboard.commands import CommandBuilder
from orchestrator.dashboard.file_pages import (
    DashboardResponse,
    e,
    error_response,
    file_route,
    html_response,
    json_html,
    state_preview,
)
from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.run_page import file_links, run_page, warnings_section
from orchestrator.dashboard.scanner import RunScanner

__all__ = ["DashboardApp", "DashboardResponse", "serve_dashboard"]


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
            return error_response(405, "Method not allowed")
        parsed = urlsplit(target)
        if parsed.path == "/":
            return DashboardResponse(status=302, headers={"Location": "/runs"})
        query = parse_qs(parsed.query)
        if parsed.path == "/runs":
            return self._runs_index(query, request_now)
        segments = [unquote(segment) for segment in parsed.path.strip("/").split("/") if segment]
        if len(segments) >= 3 and segments[0] == "runs":
            return self._run_route(segments, query, request_now)
        return error_response(404, "Not found")

    def _run_route(self, segments: list[str], query: Mapping[str, list[str]], now: datetime) -> DashboardResponse:
        workspace_id, run_dir_id, rest = segments[1], segments[2], segments[3:]
        links_files = not rest or (len(rest) >= 2 and rest[0] == "steps")
        detail = self._find_detail(workspace_id, run_dir_id, now, attempt_files=links_files)
        if detail is None:
            return error_response(404, "Run not found")
        if not rest:
            commands = CommandBuilder().build(self._run_record_for_detail(detail))
            return html_response(run_page(detail, commands, refresh=self._refresh_seconds(query)))
        if detail.row.display_status == "retired":
            return error_response(404, detail.row.failure_summary)
        if rest == ["state"]:
            return state_preview(detail)
        if len(rest) >= 2 and rest[0] == "steps":
            return self._step_detail(detail, "/".join(rest[1:]))
        if len(rest) >= 3 and rest[0] == "files":
            return file_route(detail, scope=rest[1], route_path="/".join(rest[2:]),
                              raw=self._first(query, "raw") == "1")
        return error_response(404, "Not found")

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
            *warnings_section(scan.errors),
            "<table>",
            "<thead><tr><th>Workspace</th><th>Run</th><th>State Run ID</th><th>Workflow</th><th>Status</th><th>Cursor</th><th>Started</th><th>Elapsed</th><th>Updated</th><th>Read time</th><th>Failure</th></tr></thead>",
            "<tbody>",
        ])
        if not rows:
            lines.append("<tr><td colspan=\"11\">No runs matched.</td></tr>")
        for row in rows:
            detail_href = f"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}"
            elapsed = self._format_duration(row.elapsed_seconds) if row.elapsed_seconds is not None else ""
            lines.append(
                "<tr>"
                f"<td>{e(row.workspace_label)}<br><small>{e(str(row.workspace_root))}</small></td>"
                f"<td><a href=\"{detail_href}\">{e(row.run_dir_id)}</a></td>"
                f"<td>{e(row.state_run_id or '')}</td>"
                f"<td>{e(row.workflow_file or '')}</td>"
                f"<td>{e(row.display_status)}</td>"
                f"<td>{e(row.cursor_summary)}</td>"
                f"<td>{e(row.started_at or '')}</td>"
                f"<td>{e(elapsed)}</td>"
                f"<td>{e(row.updated_at or '')}</td>"
                f"<td>{e(row.read_time or '')}</td>"
                f"<td>{e(row.failure_summary)}</td>"
                "</tr>"
            )
        lines.extend(["</tbody></table>", "</main>", "</body></html>"])
        return html_response("\n".join(lines))

    def _find_detail(self, workspace_id: str, run_dir_id: str, now: datetime, *, attempt_files: bool = False):
        scan = self.scanner.scan()
        for run in scan.runs:
            if run.workspace.id == workspace_id and run.run_dir_id == run_dir_id:
                return RunProjector(now=now).project_detail(run, attempt_files=attempt_files)
        return None

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
            return error_response(404, "Step not found")
        lines = [
            "<!doctype html>",
            "<html><head><meta charset=\"utf-8\"><title>Step Detail</title></head><body><main>",
            f"<h1>{e(step.name)}</h1>",
            f"<p>Status: {e(step.status)}</p>",
            f"<p>Kind: {e(step.kind)}</p>",
            f"<p>Step id: {e(step.step_id or '')}</p>",
            f"<p>Duration: {e(str(step.duration_ms) + ' ms' if step.duration_ms is not None else '')}</p>",
            f"<p>Attempt: {e(step.attempt if step.attempt is not None else '')}</p>",
            f"<p>Started: {e(step.started_at or '')}</p>",
            f"<p>Completed: {e(step.completed_at or '')}</p>",
            "<h2>Output Preview</h2>",
            f"<pre>{e(step.output_preview)}</pre>",
            "<h2>Error</h2>",
            f"<pre>{json_html(step.error)}</pre>",
            "<h2>Outcome</h2>",
            f"<pre>{json_html(step.outcome)}</pre>",
        ]
        if step.file_refs:
            lines.append("<h2>Files</h2>")
            lines.extend(file_links(row, step.file_refs))
        lines.extend([
            f"<p><a href=\"/runs/{quote(row.workspace_id)}/{quote(row.run_dir_id)}\">Back to run</a></p>",
            "</main></body></html>",
        ])
        return html_response("\n".join(lines))

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
        filters = {key: self._first(query, key) for key in ("workspace", "status", "workflow", "search")}
        recency = self._parse_recency(self._first(query, "recency"))
        filtered = [row for row in rows if self._row_matches(row, filters, recency, now)]
        filtered.sort(key=self._run_recency_sort_key)
        return filtered

    def _row_matches(self, row, filters: Mapping[str, Optional[str]], recency: Optional[timedelta],
                     now: datetime) -> bool:
        workspace, status, workflow, search = (filters[key] for key in ("workspace", "status", "workflow", "search"))
        if workspace and workspace not in {row.workspace_id, row.workspace_label, str(row.workspace_root)}:
            return False
        if status and status != row.display_status:
            return False
        if workflow and workflow.lower() not in (row.workflow_file or "").lower():
            return False
        if search and search.lower() not in self._search_text(row):
            return False
        return recency is None or self._updated_within(row, recency, now)

    def _search_text(self, row) -> str:
        return " ".join(
            [row.run_dir_id, row.state_run_id or "", row.workflow_file or "", row.failure_summary or ""]
        ).lower()

    def _updated_within(self, row, recency: timedelta, now: datetime) -> bool:
        updated_at = self._parse_datetime(row.updated_at)
        return updated_at is not None and now - updated_at <= recency

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
        started_at = self._parse_datetime(row.started_at)
        if started_at is not None:
            return started_at.timestamp()
        return float("-inf")

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

    def _format_duration(self, seconds_value: float) -> str:
        seconds = int(seconds_value)
        if seconds < 60:
            return f"{seconds}s"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes}m"


def host_allowed(host_header: Optional[str], bound_host: str, bound_port: int) -> bool:
    """DNS-rebinding guard: the `Host` header must name a loopback name or the bound host, with the bound port.

    A missing header is refused: every browser sends one, so only a non-browser client can omit it.
    """
    if not host_header:
        return False
    names = {"127.0.0.1", "localhost", "[::1]", f"[{bound_host}]" if ":" in bound_host else bound_host}
    allowed = {f"{name}:{bound_port}" for name in names} | (names if bound_port == 80 else set())
    return host_header.strip().lower() in {name.lower() for name in allowed}


def make_dashboard_server(*, scanner: RunScanner, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Bind the dashboard; requests whose `Host` fails `host_allowed` get 421 before any route work."""
    app = DashboardApp(scanner)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
            if host_allowed(self.headers.get("Host"), host, self.server.server_address[1]):
                response = app.handle("GET", self.path)
            else:
                response = error_response(421, "Misdirected request: Host header is not this dashboard")
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            print(format % args, file=sys.stderr)

    return ThreadingHTTPServer((host, port), Handler)


def serve_dashboard(*, scanner: RunScanner, host: str = "127.0.0.1", port: Optional[int] = None) -> int:
    """Serve the dashboard until interrupted."""
    server = make_dashboard_server(scanner=scanner, host=host, port=8765 if port is None else port)
    actual_host, actual_port = server.server_address[:2]
    print(f"Dashboard listening on http://{actual_host}:{actual_port}/runs")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
