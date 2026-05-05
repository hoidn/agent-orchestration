"""Polling watcher for managed provider file changes."""

from __future__ import annotations

from pathlib import Path

from .classifier import classify_path
from .models import ManagedJobPolicy
from .pending_policy import append_pending_record


class PollingManagedJobWatcher:
    """Deterministic polling watcher used by managed provider guard supervision."""

    def __init__(
        self,
        *,
        workspace: Path,
        watch_roots: tuple[str, ...],
        policy: ManagedJobPolicy,
        pending_path: Path,
    ) -> None:
        self.workspace = workspace.resolve()
        self.watch_roots = tuple(watch_roots)
        self.policy = policy
        self.pending_path = pending_path
        self._seen: dict[str, int] = {}

    def snapshot(self) -> None:
        """Record the current watched file mtimes without emitting decisions."""

        self._seen = self._scan()

    def poll_once(self) -> None:
        """Scan once and append pending records for new or edited files."""

        current = self._scan()
        for relpath, mtime_ns in sorted(current.items()):
            if self._seen.get(relpath) == mtime_ns:
                continue
            decision = classify_path(Path(relpath), self.policy)
            if decision.decision == "unmanaged" and decision.entry is None:
                continue
            append_pending_record(
                self.pending_path,
                {
                    "path": relpath,
                    "decision": decision.decision,
                    "reason": decision.reason,
                    "entry_id": decision.entry.id if decision.entry is not None else None,
                },
            )
        self._seen = current

    def _scan(self) -> dict[str, int]:
        files: dict[str, int] = {}
        for watch_root in self.watch_roots:
            root = (self.workspace / watch_root).resolve()
            if not self._is_within_workspace(root) or not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                resolved = path.resolve()
                if not self._is_within_workspace(resolved):
                    continue
                relpath = resolved.relative_to(self.workspace).as_posix()
                files[relpath] = resolved.stat().st_mtime_ns
        return files

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace)
        except ValueError:
            return False
        return True
