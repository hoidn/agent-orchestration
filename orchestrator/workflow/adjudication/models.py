"""Shared adjudicated-provider runtime data models and constants."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

BASELINE_COPY_POLICY = "adjudicated_provider.baseline_copy.v1"
LOCAL_SECRET_DENYLIST = "adjudicated_provider.local_secret_denylist.v1"
SCORE_ROW_SCHEMA = "adjudicated_provider.score.v1"
EVALUATION_PACKET_SCHEMA = "adjudication.evaluation_packet.v1"
EVALUATOR_JSON_CONTRACT = "adjudication.evaluator_json.v1"
SECRET_DETECTION_POLICY = "workflow_declared_secrets.v1"

_EXCLUDED_ROOT_NAMES = {
    ".orchestrate",
    ".git",
    ".venv",
    "venv",
    "env",
    ".tox",
    ".nox",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_SECRET_DIR_SUFFIXES = {
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
}
_SECRET_FILE_NAMES = {
    ".netrc",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials.json",
    "token.json",
    "service-account.json",
}
_SECRET_FILE_SUFFIXES = {".pem", ".p12", ".pfx", ".key", ".kubeconfig"}


class BaselineExcludedPathError(RuntimeError):
    """Raised when a required path is excluded from the baseline policy."""

    def __init__(self, surface: str, path: str, reason: str) -> None:
        self.surface = surface
        self.path = path
        self.reason = reason
        self.failure_type = "baseline_excluded_required_path"
        super().__init__(f"{surface} required path '{path}' excluded from baseline: {reason}")


class PromotionConflictError(RuntimeError):
    """Raised when selected output promotion would overwrite changed parent state."""

    def __init__(self, message: str, *, failure_type: str = "promotion_conflict") -> None:
        self.failure_type = failure_type
        super().__init__(message)


class EvidencePacketError(RuntimeError):
    """Raised when score-critical evidence cannot be embedded completely."""

    def __init__(self, failure_type: str, message: str) -> None:
        self.failure_type = failure_type
        super().__init__(message)


class EvaluatorOutputError(RuntimeError):
    """Raised when evaluator stdout is not valid score JSON."""


class LedgerConflictError(RuntimeError):
    """Raised when a workspace-visible score ledger mirror has a different owner."""


@dataclass(frozen=True)
class PathSurface:
    """One orchestrator-managed path that must be compared against the baseline."""

    surface: str
    path: Path


@dataclass(frozen=True)
class AdjudicationVisitPaths:
    adjudication_root: Path
    baseline_root: Path
    baseline_workspace: Path
    baseline_manifest_path: Path
    run_score_ledger_path: Path
    scorer_root: Path
    promotion_manifest_path: Path


@dataclass(frozen=True)
class CandidateRuntimePaths:
    candidate_root: Path
    workspace: Path
    stdout_log: Path
    stderr_log: Path
    prompt_path: Path
    evaluation_packet_path: Path
    evaluation_output_path: Path
    evaluation_stderr_log: Path
    evaluator_workspace: Path


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    entry_type: str
    reason: str | None = None
    size: int | None = None
    sha256: str | None = None
    mode: int | None = None
    link_text: str | None = None
    resolved_target: str | None = None


@dataclass(frozen=True)
class BaselineManifest:
    copy_policy: str
    local_secret_denylist: str
    workflow_checksum: str
    parent_workspace: str
    baseline_workspace: str
    resolved_consumes: Mapping[str, Any]
    included: tuple[ManifestEntry, ...]
    excluded: tuple[ManifestEntry, ...]
    null_path_results: Mapping[str, Any]
    baseline_digest: str

    def included_by_path(self) -> dict[str, ManifestEntry]:
        return {entry.path: entry for entry in self.included}

    def excluded_by_path(self) -> dict[str, ManifestEntry]:
        return {entry.path: entry for entry in self.excluded}


@dataclass(frozen=True)
class PromotionResult:
    status: str
    promoted_paths: dict[str, str]
    manifest_path: Path


@dataclass(frozen=True)
class SelectionResult:
    selected_candidate_id: str | None
    selected_score: float | None
    selection_reason: str
    error_type: str | None = None


@dataclass(frozen=True)
class AdjudicationDeadline:
    started_monotonic: float
    timeout_sec: float | None

    @classmethod
    def start(cls, timeout_sec: float | None) -> "AdjudicationDeadline":
        return cls(started_monotonic=time.monotonic(), timeout_sec=timeout_sec)

    def remaining_timeout_sec(self, now: float | None = None) -> float | None:
        if self.timeout_sec is None:
            return None
        current = time.monotonic() if now is None else now
        return max(0.0, float(self.timeout_sec) - (current - self.started_monotonic))

    def require_time_remaining(self, phase: str, now: float | None = None) -> None:
        remaining = self.remaining_timeout_sec(now)
        if remaining is not None and remaining <= 0:
            raise TimeoutError(f"adjudicated provider deadline expired before {phase}")

def adjudication_outcome(error_type: str) -> dict[str, Any]:
    matrix = {
        "adjudication_no_valid_candidates": (2, "post_execution", "adjudication_no_valid_candidates", False),
        "adjudication_scorer_unavailable": (2, "execution", "adjudication_scorer_unavailable", False),
        "adjudication_partial_scoring_failed": (2, "execution", "adjudication_partial_scoring_failed", False),
        "timeout": (124, "execution", "timeout", True),
        "ledger_path_collision": (2, "post_execution", "ledger_path_collision", False),
        "ledger_conflict": (2, "post_execution", "ledger_conflict", False),
        "ledger_mirror_failed": (2, "post_execution", "ledger_mirror_failed", False),
        "promotion_conflict": (2, "post_execution", "promotion_conflict", False),
        "promotion_validation_failed": (2, "post_execution", "promotion_validation_failed", False),
        "promotion_rollback_conflict": (2, "post_execution", "promotion_rollback_conflict", False),
        "adjudication_resume_mismatch": (2, "pre_execution", "adjudication_resume_mismatch", False),
    }
    exit_code, phase, klass, retryable = matrix.get(error_type, (2, "execution", error_type, False))
    return {
        "exit_code": exit_code,
        "outcome": {
            "status": "failed",
            "phase": phase,
            "class": klass,
            "retryable": retryable,
        },
    }
