"""Data and error types owned by the lean-pilot runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class RunnerError(ValueError):
    """The locked block cannot be executed without violating its protocol."""


class QuiescenceError(RunnerError):
    """A launched process group could not be proven quiescent."""


class SharedContrastInvalidation(RunnerError):
    """A shared launch fault invalidated the three-treatment contrast."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ArmCommand:
    treatment_id: str
    opaque_arm_label: str
    command_digest: str
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    timeout_milliseconds: int
    workspace: Path
    runtime_root: Path
    result_path: Path


@dataclass(frozen=True)
class ArmExecution:
    opaque_arm_label: str
    treatment_id: str
    command_digest: str
    lifecycle_outcome: str
    product_frozen: bool
    product_manifest_digest: str | None
    provider_call_count: int
    elapsed_milliseconds: int
    evidence_references: tuple[str, ...]
    token_counts: object
    cost: object

    def to_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "opaque_arm_label": self.opaque_arm_label,
            "treatment_id": self.treatment_id,
            "command_digest": self.command_digest,
            "lifecycle_outcome": self.lifecycle_outcome,
            "product_frozen": self.product_frozen,
            "provider_call_count": self.provider_call_count,
            "elapsed_milliseconds": self.elapsed_milliseconds,
            "evidence_references": list(self.evidence_references),
            "token_counts": self.token_counts,
            "cost": self.cost,
        }
        if self.product_manifest_digest is not None:
            record["product_manifest_digest"] = self.product_manifest_digest
        return record


@dataclass(frozen=True)
class BlockAttempt:
    record: dict[str, Any]
    path: Path


@dataclass(frozen=True)
class _PreparedArm:
    command: ArmCommand
    staged_assets: tuple[tuple[Path, bytes], ...]
    credential_names: tuple[str, ...]


@dataclass(frozen=True)
class _Preflight:
    repo: Path
    treeish: str
    archive_digest: str
    source_task_path: PurePosixPath
    task_brief_digest: str
    exclusions: tuple[PurePosixPath, ...]
    visible_check_argv: tuple[str, ...]
    visible_check_timeout_milliseconds: int
    maximum_start_skew_milliseconds: int
    quiescence_grace_milliseconds: int
    arms: tuple[_PreparedArm, ...]
    attempt_class: str
    sequence_index: int
    record_path: Path


@dataclass(frozen=True)
class _RawResult:
    terminal_outcome: str
    provider_call_count: int
    token_counts: object
    cost: object
