"""Dashboard read-model dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class WorkspaceRecord:
    """A resolved workspace root accepted by the dashboard scanner."""

    id: str
    root: Path
    label: str


@dataclass(frozen=True)
class RunRecord:
    """A discovered run candidate keyed by scanned workspace and run directory."""

    workspace: WorkspaceRecord
    run_dir_id: str
    run_root: Path
    state_path: Path
    state: Optional[Mapping[str, Any]] = None
    state_run_id: Optional[str] = None
    read_error: Optional[str] = None
    parse_error: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    retired: bool = False


@dataclass(frozen=True)
class ScanResult:
    """Result of request-time workspace scanning."""

    workspaces: list[WorkspaceRecord]
    runs: list[RunRecord]
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FileReference:
    """A route-scoped reference to a workspace or run-local file."""

    scope: str
    route_path: str
    absolute_path: Path
    exists: bool
    status: str = "ok"
    label: Optional[str] = None
    warning: Optional[str] = None


@dataclass(frozen=True)
class PreviewResult:
    """Escaped preview metadata for a file body."""

    path: Path
    status: str
    display_text: str = ""
    size_bytes: Optional[int] = None
    truncated: bool = False
    is_binary: bool = False
    headers: Mapping[str, str] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass(frozen=True)
class RawFileResult:
    """Raw download response metadata for a file body."""

    path: Path
    status: str
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass(frozen=True)
class DashboardStep:
    """One dashboard timeline step."""

    ref: str
    name: str
    status: str
    kind: str = "unknown"
    step_id: Optional[str] = None
    duration_ms: Any = None
    output_preview: str = ""
    error: Any = None
    outcome: Any = None
    file_refs: Mapping[str, FileReference] = field(default_factory=dict)
    attempt: Optional[int] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass(frozen=True)
class DashboardIndexRow:
    """One row in the dashboard run index."""

    workspace_id: str
    workspace_label: str
    workspace_root: Path
    run_dir_id: str
    run_root: Path
    state_path: Path
    state_run_id: Optional[str]
    workflow_file: Optional[str] = None
    display_status: str = "unknown"
    cursor_summary: str = ""
    started_at: Any = None
    updated_at: Any = None
    elapsed_seconds: Optional[float] = None
    read_time: Optional[str] = None
    failure_summary: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardRunDetail:
    """Run-detail read model for dashboard pages."""

    row: DashboardIndexRow
    steps: list[DashboardStep] = field(default_factory=list)
    cursor: Any = None
    bound_inputs: Mapping[str, Any] = field(default_factory=dict)
    workflow_outputs: Any = None
    error: Any = None
    warnings: list[str] = field(default_factory=list)
    state: Optional[Mapping[str, Any]] = None
