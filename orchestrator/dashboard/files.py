"""Safe dashboard file reference resolution."""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import Literal

from orchestrator.dashboard.models import FileReference


class UnsafePathError(ValueError):
    """Raised when a state-provided path cannot be safely route-scoped."""


class FileReferenceResolver:
    """Resolve workspace-relative and run-relative references under trusted roots."""

    def __init__(self, workspace_root: str | Path, run_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve(strict=True)
        self.run_root = Path(run_root).resolve(strict=True)
        self._ensure_under(self.run_root, self.workspace_root)

    def workspace_ref(self, value: str | Path, *, label: str | None = None) -> FileReference:
        path = self._coerce_relative(value)
        return self._make_ref("workspace", self.workspace_root, self.workspace_root / path, label)

    def run_ref(self, value: str | Path, *, label: str | None = None) -> FileReference:
        path = self._coerce_relative(value)
        return self._make_ref("run", self.run_root, self.run_root / path, label)

    def from_any(self, value: str | Path, *, label: str | None = None) -> FileReference:
        path = Path(value)
        self._reject_parent_components(path)
        if not path.is_absolute():
            return self.workspace_ref(path, label=label)

        resolved = path.resolve(strict=False)
        if self._is_under(resolved, self.run_root):
            return self._make_ref("run", self.run_root, path, label)
        if self._is_under(resolved, self.workspace_root):
            return self._make_ref("workspace", self.workspace_root, path, label)
        raise UnsafePathError(f"path is outside the selected workspace and run roots: {value}")

    def _coerce_relative(self, value: str | Path) -> Path:
        path = Path(value)
        self._reject_parent_components(path)
        if path.is_absolute():
            raise UnsafePathError(f"path must be relative for this route scope: {value}")
        return path

    def _make_ref(
        self,
        scope: Literal["workspace", "run"],
        root: Path,
        candidate: Path,
        label: str | None,
    ) -> FileReference:
        candidate = candidate.expanduser()
        if candidate.is_symlink() and not candidate.exists():
            return FileReference(
                scope=scope,
                route_path=self._route_path(root, candidate),
                absolute_path=candidate.absolute(),
                exists=False,
                status="broken_symlink",
                label=label,
            )

        resolved = candidate.resolve(strict=False)
        self._ensure_under(resolved, root)
        exists = resolved.exists()
        status = "ok" if exists else "missing"
        if exists and not resolved.is_file():
            status = "not_file"
        return FileReference(
            scope=scope,
            route_path=self._route_path(root, resolved if exists else candidate),
            absolute_path=resolved,
            exists=exists,
            status=status,
            label=label,
        )

    def _route_path(self, root: Path, path: Path) -> str:
        try:
            relative = path.resolve(strict=False).relative_to(root)
        except ValueError:
            relative = path.absolute().relative_to(root)
        return relative.as_posix()

    def _reject_parent_components(self, path: PurePath) -> None:
        if ".." in path.parts:
            raise UnsafePathError(f"path traversal is not allowed: {path}")

    def _ensure_under(self, path: Path, root: Path) -> None:
        if not self._is_under(path, root):
            raise UnsafePathError(f"path is outside allowed root: {path}")

    def _is_under(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True
