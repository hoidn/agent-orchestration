"""Managed-job path classification."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from .models import ManagedJobPolicy, ManagedJobPolicyEntry


@dataclass(frozen=True)
class ClassificationDecision:
    """One managed-job classification decision."""

    decision: str
    reason: str
    entry: ManagedJobPolicyEntry | None = None


def _matches(entry_path: str, relpath: str) -> bool:
    return entry_path == relpath or fnmatch(relpath, entry_path)


def classify_path(path: Path, policy: ManagedJobPolicy) -> ClassificationDecision:
    """Classify a workspace-relative path against managed-job policy."""

    relpath = path.as_posix()
    for entry in policy.entries:
        if not _matches(entry.path, relpath):
            continue
        if entry.mode in {"force_local", "unmanaged"}:
            return ClassificationDecision("unmanaged", f"matched {entry.mode}", entry)
        if entry.metadata is None:
            return ClassificationDecision("invalid", "managed entry lacks metadata", entry)
        return ClassificationDecision("managed", f"matched {entry.mode}", entry)
    return ClassificationDecision("unmanaged", "no matching policy entry", None)
