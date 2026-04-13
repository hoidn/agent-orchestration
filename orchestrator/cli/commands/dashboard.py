"""Dashboard command implementation."""

from __future__ import annotations

import sys
from typing import Callable, Iterable, Optional

from orchestrator.dashboard.scanner import RunScanner


def dashboard_workflow(
    workspace: Iterable[str],
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    *,
    serve: Optional[Callable[..., int]] = None,
    **_: object,
) -> int:
    """Validate dashboard workspaces and start the local read-only server."""
    try:
        scanner = RunScanner(workspace)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if serve is None:
        from orchestrator.dashboard.server import serve_dashboard

        serve = serve_dashboard
    return serve(scanner=scanner, host=host, port=port)
