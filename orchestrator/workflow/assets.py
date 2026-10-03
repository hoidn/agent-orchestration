"""Workflow-source-relative asset resolution helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from orchestrator._common.io_text import read_text_with_sha256 as _read_text_with_sha256
from orchestrator._common.safe_tree import resolve_path_preserving_fd

class AssetResolutionError(ValueError):
    """Raised when a workflow-source-relative asset path is invalid."""


class WorkflowAssetResolver:
    """Resolve source-relative assets against an authored workflow file."""

    def __init__(self, workflow_path: Path):
        resolved_workflow = resolve_path_preserving_fd(workflow_path)
        self.workflow_path = resolved_workflow
        self.source_root = resolved_workflow.parent

    def resolve(self, relative_path: str) -> Path:
        """Resolve one literal asset path under the workflow source tree."""
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise AssetResolutionError("asset paths must be non-empty strings")
        if "${" in relative_path:
            raise AssetResolutionError("asset paths must be literal workflow-source-relative strings")

        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise AssetResolutionError(f"absolute asset paths are not allowed: {relative_path}")
        if ".." in candidate.parts:
            raise AssetResolutionError(
                f"asset path traversal outside the workflow source tree is not allowed: {relative_path}"
            )

        resolved = resolve_path_preserving_fd(self.source_root / candidate)
        try:
            resolved.relative_to(self.source_root)
        except ValueError as exc:
            raise AssetResolutionError(
                f"asset path traversal outside the workflow source tree is not allowed: {relative_path}"
            ) from exc
        return resolved

    def read_text(self, relative_path: str) -> str:
        """Read one source-relative asset as UTF-8 text."""
        text, _digest = self.read_text_with_sha256(relative_path)
        return text

    def read_text_with_sha256(self, relative_path: str) -> tuple[str, str]:
        """Read one source-relative asset and retain its raw-byte digest."""
        return _read_text_with_sha256(self.resolve(relative_path), encoding="utf-8")

    def render_content_blocks(self, relative_paths: Iterable[str]) -> str:
        """Render deterministic source-asset content blocks in authored order."""
        sections: list[str] = []
        for relative_path in relative_paths:
            content = self.read_text(relative_path)
            sections.append(f"=== File: {relative_path} ===")
            sections.append(content.rstrip("\n"))
        return "\n".join(sections).rstrip()
