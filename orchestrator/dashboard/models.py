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
    visit_count: Any = None
    duration_ms: Any = None
    output_preview: str = ""
    error: Any = None
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    debug: Mapping[str, Any] = field(default_factory=dict)
    file_refs: Mapping[str, FileReference] = field(default_factory=dict)


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
    workflow_name: Optional[str] = None
    persisted_status: str = "unknown"
    display_status: str = "unknown"
    display_status_reason: Optional[str] = None
    cursor_summary: str = ""
    started_at: Any = None
    updated_at: Any = None
    state_mtime: Optional[float] = None
    read_time: Optional[str] = None
    failure_summary: str = ""
    warnings: list[str] = field(default_factory=list)
    availability: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardRunDetail:
    """Run-detail read model for dashboard pages."""

    row: DashboardIndexRow
    steps: list[DashboardStep] = field(default_factory=list)
    cursor: Any = None
    bound_inputs: Mapping[str, Any] = field(default_factory=dict)
    workflow_outputs: Mapping[str, Any] = field(default_factory=dict)
    finalization: Mapping[str, Any] = field(default_factory=dict)
    error: Any = None
    artifact_versions: Mapping[str, Any] = field(default_factory=dict)
    artifact_consumes: Mapping[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    state: Optional[Mapping[str, Any]] = None
