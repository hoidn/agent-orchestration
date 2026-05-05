"""Typed managed-job policy, audit, and identity models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ManagedJobOutcome(str, Enum):
    """Managed-job recovery outcomes."""

    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    INVALID = "INVALID"
    OUTSTANDING = "OUTSTANDING"


@dataclass(frozen=True)
class ManagedJobsRuntimeConfig:
    """Resolved runtime configuration for one managed provider step visit."""

    policy_path: Path
    watch_roots: tuple[Path, ...]
    backend: str
    poll_budget_sec: int
    audit_path: Path


@dataclass(frozen=True)
class ManagedJobMetadata:
    """Deterministic state and verification metadata for one managed entry."""

    name_template: str
    state_root_template: str
    output_root_arg: str | None
    verify_files: tuple[str, ...]
    snapshot_roots: tuple[str, ...]
    config_globs: tuple[str, ...]
    extractor: str | None = None
    extractor_version: str | None = None


@dataclass(frozen=True)
class ManagedJobPolicyEntry:
    """One normalized managed-job policy entry."""

    id: str
    mode: str
    path: str
    backend: str | None = None
    metadata: ManagedJobMetadata | None = None


@dataclass(frozen=True)
class ManagedJobPolicy:
    """Normalized managed-job policy."""

    entries: tuple[ManagedJobPolicyEntry, ...]
    default_backend: str = "auto"
