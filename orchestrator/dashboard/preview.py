"""Safe capped file previews for the local dashboard."""

from __future__ import annotations

import html
import json
from pathlib import Path

from orchestrator.dashboard.models import PreviewResult, RawFileResult


DASHBOARD_CSP = (
    "default-src 'none'; base-uri 'none'; object-src 'none'; "
    "frame-ancestors 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:"
)


class PreviewRenderer:
    """Read file bodies as inert text or safe attachment responses."""

    def __init__(self, max_bytes: int = 64 * 1024) -> None:
        self.max_bytes = max_bytes

    def preview(self, path: str | Path) -> PreviewResult:
        file_path = Path(path)
        headers = self.preview_headers()
        try:
            before = file_path.stat()
        except FileNotFoundError:
            return PreviewResult(path=file_path, status="missing", headers=headers)
        except OSError as exc:
            return PreviewResult(path=file_path, status="unreadable", headers=headers, error=str(exc))
        if not file_path.is_file():
            return PreviewResult(
                path=file_path,
                status="not_file",
                size_bytes=before.st_size,
                headers=headers,
            )

        try:
            with file_path.open("rb") as handle:
                data = handle.read(self.max_bytes + 1)
            after = file_path.stat()
        except FileNotFoundError:
            return PreviewResult(path=file_path, status="missing", headers=headers)
        except OSError as exc:
            return PreviewResult(
                path=file_path,
                status="unreadable",
                size_bytes=before.st_size,
                headers=headers,
                error=str(exc),
            )

        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return PreviewResult(
                path=file_path,
                status="changed",
                size_bytes=after.st_size,
                headers=headers,
            )

        truncated = len(data) > self.max_bytes
        if truncated:
            data = data[: self.max_bytes]
        if self._looks_binary(data):
            return PreviewResult(
                path=file_path,
                status="binary",
                size_bytes=before.st_size,
                truncated=truncated,
                is_binary=True,
                headers=headers,
            )

        text = data.decode("utf-8", errors="replace")
        display_text = self._format_display_text(file_path, text)
        return PreviewResult(
            path=file_path,
            status="ok",
            display_text=display_text,
            size_bytes=before.st_size,
            truncated=truncated or before.st_size > len(data),
            headers=headers,
        )

    def raw(self, path: str | Path) -> RawFileResult:
        file_path = Path(path)
        try:
            data = file_path.read_bytes()
        except FileNotFoundError:
            return RawFileResult(path=file_path, status="missing", headers=self.raw_headers(False))
        except OSError as exc:
            return RawFileResult(
                path=file_path,
                status="unreadable",
                headers=self.raw_headers(False),
                error=str(exc),
            )

        is_text = not self._looks_binary(data)
        return RawFileResult(
            path=file_path,
            status="ok",
            body=data,
            headers=self.raw_headers(is_text),
        )

    def preview_headers(self) -> dict[str, str]:
        return {
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": DASHBOARD_CSP,
        }

    def raw_headers(self, is_text: bool) -> dict[str, str]:
        return {
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment; filename=download",
            "Content-Type": "text/plain; charset=utf-8" if is_text else "application/octet-stream",
        }

    def _format_display_text(self, path: Path, text: str) -> str:
        if path.suffix.lower() == ".json":
            try:
                text = json.dumps(json.loads(text), indent=2, sort_keys=True)
            except json.JSONDecodeError:
                pass
        return html.escape(text, quote=False)

    def _looks_binary(self, data: bytes) -> bool:
        return b"\x00" in data
