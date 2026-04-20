"""Adjudicated-provider runtime helpers.

This module owns deterministic sidecar paths, baseline snapshots, evidence
packet construction, selection, ledgers, and selected-output promotion. These
helpers remain together for the first adjudicated-provider tranche because the
transaction, ledger, and scorer identities share private path, hash, and preimage
primitives. Split the module once resume/retry work introduces stable submodule
boundaries. The executor coordinates these helpers; it should not duplicate
their filesystem or scoring rules.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence
from hashlib import sha256

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_expected_outputs,
    validate_output_bundle,
)


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


def adjudication_visit_paths(
    run_root: Path,
    frame_scope: str,
    step_id: str,
    visit_count: int,
) -> AdjudicationVisitPaths:
    frame = _safe_token(frame_scope, "frame_scope")
    step = _safe_token(step_id, "step_id")
    visit = _safe_visit_count(visit_count)
    adjudication_root = run_root / "adjudication" / frame / step / str(visit)
    baseline_root = adjudication_root / "baseline"
    return AdjudicationVisitPaths(
        adjudication_root=adjudication_root,
        baseline_root=baseline_root,
        baseline_workspace=baseline_root / "workspace",
        baseline_manifest_path=baseline_root / "manifest.json",
        run_score_ledger_path=adjudication_root / "candidate_scores.jsonl",
        scorer_root=adjudication_root / "scorer",
        promotion_manifest_path=run_root / "promotions" / frame / step / str(visit) / "manifest.json",
    )


def candidate_paths(
    run_root: Path,
    frame_scope: str,
    step_id: str,
    visit_count: int,
    candidate_id: str,
) -> CandidateRuntimePaths:
    frame = _safe_token(frame_scope, "frame_scope")
    step = _safe_token(step_id, "step_id")
    visit = _safe_visit_count(visit_count)
    candidate = _safe_token(candidate_id, "candidate_id")
    candidate_root = run_root / "candidates" / frame / step / str(visit) / candidate
    return CandidateRuntimePaths(
        candidate_root=candidate_root,
        workspace=candidate_root / "workspace",
        stdout_log=candidate_root / "stdout.log",
        stderr_log=candidate_root / "stderr.log",
        prompt_path=candidate_root / "prompt.txt",
        evaluation_packet_path=candidate_root / "evaluation_packet.json",
        evaluation_output_path=candidate_root / "evaluation_output.json",
        evaluator_workspace=candidate_root / "evaluator" / "workspace",
    )


def create_baseline_snapshot(
    *,
    parent_workspace: Path,
    run_root: Path,
    visit_paths: AdjudicationVisitPaths,
    workflow_checksum: str,
    resolved_consumes: Mapping[str, Any],
    required_path_surfaces: Sequence[PathSurface],
    optional_path_surfaces: Sequence[PathSurface],
) -> BaselineManifest:
    del run_root
    parent_workspace = parent_workspace.resolve()
    baseline_workspace = visit_paths.baseline_workspace
    if baseline_workspace.exists():
        shutil.rmtree(baseline_workspace)
    baseline_workspace.mkdir(parents=True, exist_ok=True)

    included: list[ManifestEntry] = []
    excluded: list[ManifestEntry] = []
    _copy_baseline_tree(parent_workspace, baseline_workspace, included, excluded)
    included.sort(key=lambda entry: entry.path)
    excluded.sort(key=lambda entry: entry.path)

    null_path_results = _build_null_path_results(
        parent_workspace=parent_workspace,
        baseline_workspace=baseline_workspace,
        included=included,
        excluded=excluded,
        required_path_surfaces=required_path_surfaces,
        optional_path_surfaces=optional_path_surfaces,
    )
    manifest_payload = {
        "copy_policy": BASELINE_COPY_POLICY,
        "local_secret_denylist": LOCAL_SECRET_DENYLIST,
        "workflow_checksum": workflow_checksum,
        "parent_workspace": parent_workspace.as_posix(),
        "baseline_workspace": baseline_workspace.as_posix(),
        "resolved_consumes": _jsonable(resolved_consumes),
        "included": [asdict(entry) for entry in included],
        "excluded": [asdict(entry) for entry in excluded],
        "null_path_results": null_path_results,
    }
    digest = _stable_hash(manifest_payload)
    manifest_payload["baseline_digest"] = digest
    visit_paths.baseline_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(visit_paths.baseline_manifest_path, _canonical_json(manifest_payload) + "\n")
    return BaselineManifest(
        copy_policy=BASELINE_COPY_POLICY,
        local_secret_denylist=LOCAL_SECRET_DENYLIST,
        workflow_checksum=workflow_checksum,
        parent_workspace=parent_workspace.as_posix(),
        baseline_workspace=baseline_workspace.as_posix(),
        resolved_consumes=dict(resolved_consumes),
        included=tuple(included),
        excluded=tuple(excluded),
        null_path_results=null_path_results,
        baseline_digest=digest,
    )


def load_baseline_manifest(path: Path) -> BaselineManifest:
    document = json.loads(path.read_text(encoding="utf-8"))
    return BaselineManifest(
        copy_policy=document["copy_policy"],
        local_secret_denylist=document["local_secret_denylist"],
        workflow_checksum=document["workflow_checksum"],
        parent_workspace=document["parent_workspace"],
        baseline_workspace=document["baseline_workspace"],
        resolved_consumes=document.get("resolved_consumes", {}),
        included=tuple(ManifestEntry(**entry) for entry in document.get("included", [])),
        excluded=tuple(ManifestEntry(**entry) for entry in document.get("excluded", [])),
        null_path_results=document.get("null_path_results", {}),
        baseline_digest=document["baseline_digest"],
    )


def prepare_candidate_workspace_from_baseline(
    *,
    baseline_workspace: Path,
    candidate_workspace: Path,
) -> None:
    if candidate_workspace.exists():
        shutil.rmtree(candidate_workspace)
    candidate_workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(baseline_workspace, candidate_workspace, symlinks=True)


def promote_candidate_outputs(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
    baseline_manifest: BaselineManifest,
    promotion_manifest_path: Path,
) -> PromotionResult:
    candidate_workspace = candidate_workspace.resolve()
    parent_workspace = parent_workspace.resolve()
    files, promoted_paths = _promotion_file_plan(
        expected_outputs=expected_outputs,
        output_bundle=output_bundle,
        candidate_workspace=candidate_workspace,
        parent_workspace=parent_workspace,
    )
    _reject_duplicate_destinations(files)
    for file_entry in files:
        baseline_preimage = _baseline_preimage(baseline_manifest, file_entry["dest_rel"])
        current_preimage = _current_preimage(parent_workspace, file_entry["dest_rel"])
        if current_preimage != baseline_preimage:
            raise PromotionConflictError(
                f"promotion destination '{file_entry['dest_rel']}' changed from baseline"
            )
        file_entry["baseline_preimage"] = baseline_preimage
        file_entry["current_preimage"] = current_preimage
        file_entry["source_sha256"] = _hash_file(file_entry["source"])

    promotion_root = promotion_manifest_path.parent
    staging_root = promotion_root / "staging"
    backups_root = promotion_root / "backups"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    if backups_root.exists():
        shutil.rmtree(backups_root)
    staging_root.mkdir(parents=True, exist_ok=True)
    backups_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema": "adjudicated_provider.promotion.v1",
        "status": "prepared",
        "files": [_promotion_manifest_file_entry(file_entry) for file_entry in files],
        "promoted_paths": promoted_paths,
    }
    promotion_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")

    for file_entry in files:
        staged = staging_root / file_entry["dest_rel"]
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_entry["source"], staged)
        file_entry["staged"] = staged

    backups: list[tuple[Path, Path]] = []
    created_from_absent: list[Path] = []
    try:
        manifest["status"] = "committing"
        _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
        for file_entry in files:
            dest = parent_workspace / file_entry["dest_rel"]
            current_preimage = _current_preimage(parent_workspace, file_entry["dest_rel"])
            if current_preimage != file_entry["baseline_preimage"]:
                raise PromotionConflictError(
                    f"promotion destination '{file_entry['dest_rel']}' changed before commit"
                )
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                backup = backups_root / file_entry["dest_rel"]
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, backup)
                backups.append((dest, backup))
            else:
                created_from_absent.append(dest)
            _replace_file(file_entry["staged"], dest)

        try:
            if output_bundle:
                validate_output_bundle(output_bundle, workspace=parent_workspace)
            else:
                validate_expected_outputs(expected_outputs or [], workspace=parent_workspace)
        except OutputContractError as exc:
            try:
                _rollback_promoted_files(
                    files=files,
                    parent_workspace=parent_workspace,
                    backups_root=backups_root,
                )
            except PromotionConflictError as rollback_exc:
                manifest["status"] = "rolling_back"
                manifest["failure_type"] = rollback_exc.failure_type
                manifest["failure_message"] = str(rollback_exc)
                _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
                raise
            manifest["status"] = "failed"
            manifest["failure_type"] = "promotion_validation_failed"
            manifest["failure_message"] = str(exc)
            _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
            raise PromotionConflictError(str(exc), failure_type="promotion_validation_failed") from exc
    except PromotionConflictError as exc:
        if promotion_manifest_path.exists():
            try:
                if manifest.get("status") != "rolling_back":
                    manifest["status"] = "failed"
                    manifest["failure_type"] = exc.failure_type
                    manifest["failure_message"] = str(exc)
                _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
            except Exception:
                pass
        raise
    except Exception:
        if promotion_manifest_path.exists():
            try:
                manifest["status"] = "failed"
                _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
            except Exception:
                pass
        raise

    manifest["status"] = "committed"
    _atomic_write_text(promotion_manifest_path, _canonical_json(manifest) + "\n")
    return PromotionResult(
        status="committed",
        promoted_paths=promoted_paths,
        manifest_path=promotion_manifest_path,
    )


def scorer_identity_hash(scorer: Mapping[str, Any]) -> str:
    return _stable_hash(
        {
            "evaluator_provider": scorer.get("evaluator_provider"),
            "evaluator_params": scorer.get("evaluator_params"),
            "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash"),
            "rubric_hash": scorer.get("rubric_hash"),
            "evaluator_json_contract": EVALUATOR_JSON_CONTRACT,
            "evaluation_packet_schema": EVALUATION_PACKET_SCHEMA,
            "evidence_limits": scorer.get("evidence_limits"),
            "evidence_confidentiality": scorer.get("evidence_confidentiality"),
            "secret_detection_policy": SECRET_DETECTION_POLICY,
        }
    )


def persist_scorer_snapshot(scorer: Mapping[str, Any], scorer_root: Path) -> Path:
    """Persist the resolved scorer identity snapshot for replay and resume checks."""
    path = scorer_root / "metadata.json"
    _atomic_write_text(path, _canonical_json(dict(scorer)) + "\n")
    return path


def persist_scorer_resolution_failure(failure: Mapping[str, Any], scorer_root: Path) -> Path:
    """Persist normalized scorer-resolution failure metadata."""
    path = scorer_root / "resolution_failure.json"
    _atomic_write_text(path, _canonical_json(dict(failure)) + "\n")
    return path


def build_evaluation_packet(
    *,
    candidate_id: str,
    candidate_workspace: Path,
    rendered_prompt: str,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    artifacts: Mapping[str, Any],
    scorer: Mapping[str, Any],
    evidence_limits: Mapping[str, int] | None,
    workflow_secret_values: Sequence[str],
    rubric_content: str | None = None,
) -> dict[str, Any]:
    limits = {
        "max_item_bytes": 262144,
        "max_packet_bytes": 1048576,
    }
    if isinstance(evidence_limits, Mapping):
        limits.update({key: int(value) for key, value in evidence_limits.items()})
    evidence_items: list[dict[str, Any]] = []
    _add_text_evidence(
        evidence_items,
        name="candidate_prompt",
        path=None,
        content=rendered_prompt,
        limits=limits,
        workflow_secret_values=workflow_secret_values,
    )
    if rubric_content is not None:
        _add_text_evidence(
            evidence_items,
            name="rubric",
            path=None,
            content=rubric_content,
            limits=limits,
            workflow_secret_values=workflow_secret_values,
        )

    if output_bundle:
        bundle_path = _workspace_file(candidate_workspace, str(output_bundle.get("path", "")))
        bundle_text = _read_text_evidence(bundle_path)
        _add_text_evidence(
            evidence_items,
            name="output_bundle",
            path=str(output_bundle.get("path", "")),
            content=bundle_text,
            limits=limits,
            workflow_secret_values=workflow_secret_values,
        )
        bundle_doc = json.loads(bundle_text)
        for field_spec in output_bundle.get("fields", []):
            if (
                isinstance(field_spec, dict)
                and field_spec.get("type") == "relpath"
                and field_spec.get("must_exist_target")
            ):
                found, relpath_value = _resolve_json_pointer(bundle_doc, str(field_spec.get("json_pointer", "")))
                if found and isinstance(relpath_value, str):
                    _add_file_evidence(
                        evidence_items,
                        candidate_workspace=candidate_workspace,
                        name=f"{field_spec.get('name')}.target",
                        relpath=relpath_value,
                        limits=limits,
                        workflow_secret_values=workflow_secret_values,
                    )
    else:
        for spec in expected_outputs or []:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name", "output"))
            output_path = str(spec.get("path", ""))
            value_text = _read_text_evidence(_workspace_file(candidate_workspace, output_path))
            _add_text_evidence(
                evidence_items,
                name=f"{name}.value_file",
                path=output_path,
                content=value_text,
                limits=limits,
                workflow_secret_values=workflow_secret_values,
            )
            if spec.get("type") == "relpath" and spec.get("must_exist_target"):
                _add_file_evidence(
                    evidence_items,
                    candidate_workspace=candidate_workspace,
                    name=f"{name}.target",
                    relpath=str(artifacts.get(name, value_text.strip())),
                    limits=limits,
                    workflow_secret_values=workflow_secret_values,
                )

    total_bytes = sum(int(item["byte_size"]) for item in evidence_items)
    if total_bytes > limits["max_packet_bytes"]:
        raise EvidencePacketError("evidence_packet_too_large", "evaluation packet exceeds max_packet_bytes")
    packet = {
        "packet_schema": EVALUATION_PACKET_SCHEMA,
        "candidate_id": candidate_id,
        "scorer_identity_hash": scorer.get("scorer_identity_hash"),
        "evidence_confidentiality": "same_trust_boundary",
        "secret_detection_policy": SECRET_DETECTION_POLICY,
        "artifacts": dict(artifacts),
        "evidence_items": evidence_items,
    }
    packet["evaluation_packet_hash"] = _stable_hash(packet)
    return packet


def parse_evaluator_output(stdout: bytes | str, *, expected_candidate_id: str) -> dict[str, Any]:
    text = stdout.decode("utf-8") if isinstance(stdout, bytes) else stdout
    try:
        document = json.loads(text, parse_constant=lambda value: (_raise_invalid_constant(value)))
    except Exception as exc:
        raise EvaluatorOutputError(f"evaluator stdout must be strict JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise EvaluatorOutputError("evaluator JSON must be an object")
    if document.get("candidate_id") != expected_candidate_id:
        raise EvaluatorOutputError("evaluator candidate_id does not match")
    score = document.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)):
        raise EvaluatorOutputError("evaluator score must be a finite number")
    score = float(score)
    if score < 0.0 or score > 1.0:
        raise EvaluatorOutputError("evaluator score must be in [0.0, 1.0]")
    summary = document.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise EvaluatorOutputError("evaluator summary must be a non-empty string")
    return {
        "candidate_id": expected_candidate_id,
        "score": score,
        "summary": summary,
    }


def select_candidate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    require_score_for_single_candidate: bool,
) -> SelectionResult:
    valid = [candidate for candidate in candidates if candidate.get("candidate_status") == "output_valid"]
    if not valid:
        return SelectionResult(None, None, "none", "adjudication_no_valid_candidates")
    if len(valid) == 1:
        candidate = valid[0]
        if candidate.get("score_status") == "scored" and _is_finite_score(candidate.get("score")):
            return SelectionResult(str(candidate["candidate_id"]), float(candidate["score"]), "highest_score")
        if require_score_for_single_candidate:
            if candidate.get("score_status") == "scorer_unavailable":
                return SelectionResult(None, None, "none", "adjudication_scorer_unavailable")
            return SelectionResult(None, None, "none", "adjudication_partial_scoring_failed")
        return SelectionResult(str(candidate["candidate_id"]), None, "single_candidate_contract_valid")

    if any(candidate.get("score_status") == "scorer_unavailable" for candidate in valid):
        return SelectionResult(None, None, "none", "adjudication_scorer_unavailable")
    if any(candidate.get("score_status") != "scored" or not _is_finite_score(candidate.get("score")) for candidate in valid):
        return SelectionResult(None, None, "none", "adjudication_partial_scoring_failed")

    best_index = 0
    best_score = float(valid[0]["score"])
    tied = False
    for index, candidate in enumerate(valid[1:], start=1):
        score = float(candidate["score"])
        if score > best_score:
            best_index = index
            best_score = score
            tied = False
        elif score == best_score:
            tied = True
    selected = valid[best_index]
    return SelectionResult(
        str(selected["candidate_id"]),
        best_score,
        "candidate_order_tie_break" if tied and best_index == 0 else "highest_score",
    )


def generate_score_ledger_rows(
    *,
    run_id: str,
    workflow_file: str,
    workflow_checksum: str,
    dsl_version: str,
    execution_frame_id: str,
    call_frame_id: str | None,
    step_id: str,
    step_name: str,
    visit_count: int,
    candidates: Sequence[Mapping[str, Any]],
    selected_candidate_id: str | None,
    selection_reason: str,
    promotion_status: str,
    promoted_paths: Mapping[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = _utc_now()
    for index, candidate in enumerate(candidates):
        candidate_id = str(candidate.get("candidate_id"))
        candidate_index = int(candidate.get("candidate_index", index))
        candidate_run_key = _stable_hash(
            {
                "run_id": run_id,
                "execution_frame_id": execution_frame_id,
                "step_id": step_id,
                "visit_count": visit_count,
                "candidate_id": candidate_id,
                "candidate_config_hash": candidate.get("candidate_config_hash"),
                "composed_prompt_hash": candidate.get("composed_prompt_hash"),
            }
        )
        score_run_key = _stable_hash(_score_run_identity(candidate, candidate_run_key))
        if score_run_key in seen:
            continue
        seen.add(score_run_key)
        selected = candidate_id == selected_candidate_id
        row = {
            "row_schema": SCORE_ROW_SCHEMA,
            "score_run_key": score_run_key,
            "candidate_run_key": candidate_run_key,
            "run_id": run_id,
            "workflow_file": workflow_file,
            "workflow_checksum": workflow_checksum,
            "dsl_version": dsl_version,
            "state_schema_version": "2.1",
            "execution_frame_id": execution_frame_id,
            "call_frame_id": call_frame_id,
            "step_id": step_id,
            "step_name": step_name,
            "visit_count": visit_count,
            "candidate_id": candidate_id,
            "candidate_index": candidate_index,
            "candidate_provider": candidate.get("candidate_provider"),
            "candidate_model": candidate.get("candidate_model"),
            "candidate_params_hash": candidate.get("candidate_params_hash"),
            "candidate_config_hash": candidate.get("candidate_config_hash"),
            "prompt_variant_id": candidate.get("prompt_variant_id"),
            "prompt_source_kind": candidate.get("prompt_source_kind"),
            "prompt_source": candidate.get("prompt_source"),
            "composed_prompt_hash": candidate.get("composed_prompt_hash"),
            "candidate_status": candidate.get("candidate_status"),
            "provider_exit_code": candidate.get("provider_exit_code"),
            "attempt_count": candidate.get("attempt_count", 1),
            "score_status": candidate.get("score_status"),
            "scorer_identity_hash": candidate.get("scorer_identity_hash"),
            "scorer_resolution_failure_key": candidate.get("scorer_resolution_failure_key"),
            "evaluator_provider": candidate.get("evaluator_provider"),
            "evaluator_model": candidate.get("evaluator_model"),
            "evaluator_params_hash": candidate.get("evaluator_params_hash"),
            "evaluator_config_hash": candidate.get("evaluator_config_hash"),
            "evaluator_prompt_source_kind": candidate.get("evaluator_prompt_source_kind"),
            "evaluator_prompt_source": candidate.get("evaluator_prompt_source"),
            "evaluator_prompt_hash": candidate.get("evaluator_prompt_hash"),
            "evidence_confidentiality": candidate.get("evidence_confidentiality"),
            "secret_detection_policy": candidate.get("secret_detection_policy"),
            "rubric_source_kind": candidate.get("rubric_source_kind"),
            "rubric_source": candidate.get("rubric_source"),
            "rubric_hash": candidate.get("rubric_hash"),
            "evaluation_packet_hash": candidate.get("evaluation_packet_hash"),
            "score": candidate.get("score"),
            "selected": selected,
            "selection_reason": selection_reason if selected else "none",
            "promotion_status": promotion_status if selected else "not_selected",
            "summary": candidate.get("summary"),
            "failure_type": candidate.get("failure_type"),
            "failure_message": candidate.get("failure_message"),
            "candidate_root": candidate.get("candidate_root"),
            "candidate_workspace": candidate.get("candidate_workspace"),
            "output_paths": candidate.get("output_paths", {}),
            "promoted_paths": dict(promoted_paths) if selected and promotion_status == "committed" else {},
            "created_at": now,
        }
        rows.append(row)
    return rows


def materialize_run_score_ledger(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, "".join(_canonical_json(row) + "\n" for row in rows))


def materialize_score_ledger_mirror(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        owner = _ledger_owner(rows[0]) if rows else None
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                existing = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerConflictError(f"existing ledger mirror contains invalid JSONL at line {line_number}") from exc
            if _ledger_owner(existing) != owner:
                raise LedgerConflictError("existing ledger mirror belongs to a different adjudicated step visit")
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, "".join(_canonical_json(row) + "\n" for row in rows))


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


def _copy_baseline_tree(
    source_root: Path,
    dest_root: Path,
    included: list[ManifestEntry],
    excluded: list[ManifestEntry],
) -> None:
    for root, dir_names, file_names in os.walk(source_root, topdown=True, followlinks=False):
        root_path = Path(root)
        rel_root = _relative_posix(root_path, source_root)
        kept_dirs: list[str] = []
        for dir_name in sorted(dir_names):
            rel = _join_rel(rel_root, dir_name)
            reason = _exclude_reason(Path(rel), is_dir=True)
            full_path = root_path / dir_name
            if reason is not None:
                excluded.append(ManifestEntry(path=rel, entry_type="directory", reason=reason))
                continue
            if full_path.is_symlink():
                entry = _copy_symlink(
                    full_path,
                    dest_root / rel,
                    rel,
                    source_root,
                    included,
                    excluded,
                )
                if entry:
                    kept_dirs.append(dir_name)
                continue
            kept_dirs.append(dir_name)
        dir_names[:] = kept_dirs

        for file_name in sorted(file_names):
            rel = _join_rel(rel_root, file_name)
            source = root_path / file_name
            reason = _exclude_reason(Path(rel), is_dir=False)
            if reason is not None:
                excluded.append(ManifestEntry(path=rel, entry_type="file", reason=reason))
                continue
            if source.is_symlink():
                _copy_symlink(source, dest_root / rel, rel, source_root, included, excluded)
                continue
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            stat = source.stat()
            included.append(
                ManifestEntry(
                    path=rel,
                    entry_type="file",
                    size=stat.st_size,
                    sha256=_hash_file(source),
                    mode=stat.st_mode & 0o777,
                )
            )


def _copy_symlink(
    source: Path,
    dest: Path,
    rel: str,
    source_root: Path,
    included: list[ManifestEntry],
    excluded: list[ManifestEntry],
) -> bool:
    link_text = os.readlink(source)
    target_path = Path(link_text)
    if target_path.is_absolute():
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="absolute_symlink", link_text=link_text))
        return False
    resolved = (source.parent / target_path).resolve()
    if not _is_within(resolved, source_root):
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="escaping_symlink", link_text=link_text))
        return False
    if not resolved.exists():
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="broken_symlink", link_text=link_text))
        return False
    resolved_rel = resolved.relative_to(source_root)
    reason = _exclude_reason(resolved_rel, is_dir=resolved.is_dir())
    if reason is not None:
        excluded.append(ManifestEntry(path=rel, entry_type="symlink", reason="excluded_target_symlink", link_text=link_text))
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.symlink_to(link_text)
    included.append(
        ManifestEntry(
            path=rel,
            entry_type="symlink",
            link_text=link_text,
            resolved_target=resolved_rel.as_posix(),
        )
    )
    return resolved.is_dir()


def _build_null_path_results(
    *,
    parent_workspace: Path,
    baseline_workspace: Path,
    included: Sequence[ManifestEntry],
    excluded: Sequence[ManifestEntry],
    required_path_surfaces: Sequence[PathSurface],
    optional_path_surfaces: Sequence[PathSurface],
) -> dict[str, Any]:
    included_paths = {entry.path for entry in included}
    excluded_by_path = {entry.path: entry for entry in excluded}
    results: dict[str, Any] = {}
    for required, surfaces in ((True, required_path_surfaces), (False, optional_path_surfaces)):
        for surface in surfaces:
            rel = _safe_relpath(surface.path)
            parent = parent_workspace / rel
            baseline = baseline_workspace / rel
            excluded_entry = _matching_exclusion(rel, excluded_by_path)
            if excluded_entry is not None:
                if required and parent.exists():
                    raise BaselineExcludedPathError(surface.surface, rel, excluded_entry.reason or "excluded")
                state = "excluded"
            elif rel in included_paths or baseline.exists() or baseline.is_symlink():
                state = "included"
            elif parent.exists() or parent.is_symlink():
                state = "missing_from_baseline"
            else:
                state = "absent"
            results[surface.surface] = {
                "path": rel,
                "required": required,
                "state": state,
            }
    return results


def _promotion_file_plan(
    *,
    expected_outputs: list[dict] | None,
    output_bundle: dict | None,
    candidate_workspace: Path,
    parent_workspace: Path,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    files: list[dict[str, Any]] = []
    promoted_paths: dict[str, str] = {}
    if output_bundle:
        bundle_rel = _safe_relpath(Path(str(output_bundle.get("path", ""))))
        bundle_source = _workspace_file(candidate_workspace, bundle_rel)
        files.append({"role": "bundle", "artifact": "output_bundle", "source": bundle_source, "dest_rel": bundle_rel})
        fields = output_bundle.get("fields", [])
        bundle_doc = json.loads(bundle_source.read_text(encoding="utf-8"))
        for field_spec in fields:
            if not isinstance(field_spec, dict):
                continue
            artifact_name = str(field_spec.get("name", "artifact"))
            if field_spec.get("type") == "relpath" and field_spec.get("must_exist_target"):
                found, relpath_value = _resolve_json_pointer(bundle_doc, str(field_spec.get("json_pointer", "")))
                if found and isinstance(relpath_value, str):
                    target_rel = _safe_relpath(Path(relpath_value))
                    target_source = _workspace_file(candidate_workspace, target_rel)
                    files.append({"role": "relpath_target", "artifact": artifact_name, "source": target_source, "dest_rel": target_rel})
                    promoted_paths[f"{artifact_name}.target"] = target_rel
        return files, promoted_paths

    for spec in expected_outputs or []:
        if not isinstance(spec, dict):
            continue
        artifact_name = str(spec.get("name", "artifact"))
        value_rel = _safe_relpath(Path(str(spec.get("path", ""))))
        value_source = _workspace_file(candidate_workspace, value_rel)
        files.append({"role": "value_file", "artifact": artifact_name, "source": value_source, "dest_rel": value_rel})
        promoted_paths[artifact_name] = value_rel
        if spec.get("type") == "relpath" and spec.get("must_exist_target"):
            target_rel = _safe_relpath(Path(value_source.read_text(encoding="utf-8").strip()))
            target_source = _workspace_file(candidate_workspace, target_rel)
            files.append({"role": "relpath_target", "artifact": artifact_name, "source": target_source, "dest_rel": target_rel})
            promoted_paths[f"{artifact_name}.target"] = target_rel
    for file_entry in files:
        if not file_entry["source"].exists() or not file_entry["source"].is_file():
            raise PromotionConflictError(f"promotion source '{file_entry['source']}' is missing")
    del parent_workspace
    return files, promoted_paths


def _reject_duplicate_destinations(files: Sequence[Mapping[str, Any]]) -> None:
    seen: dict[str, Mapping[str, Any]] = {}
    for file_entry in files:
        dest = str(file_entry["dest_rel"])
        previous = seen.get(dest)
        if previous is None:
            seen[dest] = file_entry
            continue
        if _hash_file(previous["source"]) != _hash_file(file_entry["source"]) or previous["role"] != file_entry["role"]:
            raise PromotionConflictError(f"duplicate promotion destination '{dest}'")


def _baseline_preimage(manifest: BaselineManifest, relpath: str) -> dict[str, Any]:
    included = manifest.included_by_path().get(relpath)
    if included is not None:
        if included.entry_type != "file":
            return {"state": "unavailable"}
        return {
            "state": "file",
            "sha256": included.sha256,
            "mode": included.mode,
        }
    if _matching_exclusion(relpath, manifest.excluded_by_path()) is not None:
        return {"state": "unavailable"}
    return {"state": "absent"}


def _current_preimage(parent_workspace: Path, relpath: str) -> dict[str, Any]:
    path = _workspace_file(parent_workspace, relpath, must_exist=False)
    if not path.exists():
        return {"state": "absent"}
    if not path.is_file():
        return {"state": "unavailable"}
    stat = path.stat()
    return {
        "state": "file",
        "sha256": _hash_file(path),
        "mode": stat.st_mode & 0o777,
    }


def _promotion_manifest_file_entry(file_entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "role": file_entry["role"],
        "artifact": file_entry["artifact"],
        "source": str(file_entry["source"]),
        "dest_rel": file_entry["dest_rel"],
        "source_sha256": file_entry["source_sha256"],
        "baseline_preimage": file_entry["baseline_preimage"],
        "current_preimage": file_entry["current_preimage"],
    }


def _rollback_promoted_files(
    *,
    files: Sequence[Mapping[str, Any]],
    parent_workspace: Path,
    backups_root: Path,
) -> None:
    for file_entry in reversed(files):
        dest_rel = str(file_entry["dest_rel"])
        baseline_preimage = dict(file_entry["baseline_preimage"])
        source_sha256 = str(file_entry["source_sha256"])
        current_preimage = _current_preimage(parent_workspace, dest_rel)
        dest = parent_workspace / dest_rel

        if baseline_preimage.get("state") == "file":
            if _preimage_matches_hash(current_preimage, source_sha256):
                backup = backups_root / dest_rel
                if not backup.exists():
                    raise PromotionConflictError(
                        f"promotion rollback backup missing for '{dest_rel}'",
                        failure_type="promotion_rollback_conflict",
                    )
                _replace_file(backup, dest)
                continue
            if _same_file_preimage(current_preimage, baseline_preimage):
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        if baseline_preimage.get("state") == "absent":
            if _preimage_matches_hash(current_preimage, source_sha256):
                if dest.exists():
                    dest.unlink()
                continue
            if current_preimage.get("state") == "absent":
                continue
            raise PromotionConflictError(
                f"promotion destination '{dest_rel}' changed before rollback",
                failure_type="promotion_rollback_conflict",
            )

        raise PromotionConflictError(
            f"promotion destination '{dest_rel}' has unavailable baseline preimage",
            failure_type="promotion_rollback_conflict",
        )


def _preimage_matches_hash(preimage: Mapping[str, Any], sha256_value: str) -> bool:
    return preimage.get("state") == "file" and preimage.get("sha256") == sha256_value


def _same_file_preimage(current: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    if current.get("state") != expected.get("state"):
        return False
    if current.get("state") != "file":
        return current.get("state") == expected.get("state")
    return current.get("sha256") == expected.get("sha256")


def _score_run_identity(candidate: Mapping[str, Any], candidate_run_key: str) -> dict[str, Any]:
    score_status = candidate.get("score_status")
    if score_status == "scored":
        return {
            "candidate_run_key": candidate_run_key,
            "score_status": score_status,
            "scorer_identity_hash": candidate.get("scorer_identity_hash"),
            "evaluation_packet_hash": candidate.get("evaluation_packet_hash"),
        }
    if score_status == "scorer_unavailable":
        return {
            "candidate_run_key": candidate_run_key,
            "score_status": score_status,
            "scorer_resolution_failure_key": candidate.get("scorer_resolution_failure_key"),
        }
    if score_status == "evaluation_failed":
        return {
            "candidate_run_key": candidate_run_key,
            "score_status": score_status,
            "scorer_identity_hash": candidate.get("scorer_identity_hash"),
            "evaluation_packet_hash": candidate.get("evaluation_packet_hash"),
            "failure_type": candidate.get("failure_type"),
            "failure_message": candidate.get("failure_message"),
        }
    return {
        "candidate_run_key": candidate_run_key,
        "score_status": score_status or "not_evaluated",
    }


def _add_file_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    candidate_workspace: Path,
    name: str,
    relpath: str,
    limits: Mapping[str, int],
    workflow_secret_values: Sequence[str],
) -> None:
    path = _workspace_file(candidate_workspace, relpath)
    _add_text_evidence(
        evidence_items,
        name=name,
        path=relpath,
        content=_read_text_evidence(path),
        limits=limits,
        workflow_secret_values=workflow_secret_values,
    )


def _add_text_evidence(
    evidence_items: list[dict[str, Any]],
    *,
    name: str,
    path: str | None,
    content: str,
    limits: Mapping[str, int],
    workflow_secret_values: Sequence[str],
) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > int(limits["max_item_bytes"]):
        raise EvidencePacketError("evidence_item_too_large", f"score-critical evidence item '{name}' exceeds max_item_bytes")
    for secret_value in workflow_secret_values:
        if isinstance(secret_value, str) and secret_value and secret_value in content:
            raise EvidencePacketError("secret_detected_in_score_evidence", "score-critical evidence contains a workflow-declared secret")
    evidence_items.append(
        {
            "name": name,
            "path": path,
            "byte_size": len(encoded),
            "sha256": _hash_bytes(encoded),
            "content": content,
        }
    )


def _read_text_evidence(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EvidencePacketError("non_utf8_score_evidence", f"score-critical evidence '{path}' is not UTF-8") from exc
    except OSError as exc:
        raise EvidencePacketError("score_evidence_read_failed", f"score-critical evidence '{path}' cannot be read") from exc


def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    current = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue
        return False, None
    return True, current


def _raise_invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _ledger_owner(row: Mapping[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        row.get("row_schema"),
        row.get("run_id"),
        row.get("execution_frame_id"),
        row.get("step_id"),
        row.get("visit_count"),
    )


def _exclude_reason(relpath: Path, *, is_dir: bool) -> str | None:
    parts = relpath.parts
    if not parts:
        return None
    if any(part in _EXCLUDED_ROOT_NAMES for part in parts):
        return "excluded_root"
    if is_dir and any(part in _SECRET_DIR_SUFFIXES for part in parts):
        return "secret_denylist"
    name = parts[-1]
    if name == ".env":
        return "secret_denylist"
    if name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"}:
        return "secret_denylist"
    if name in _SECRET_FILE_NAMES:
        return "secret_denylist"
    if name in {"config.json"} and len(parts) >= 2 and parts[-2] == ".docker":
        return "secret_denylist"
    if relpath.as_posix().endswith(".config/gcloud"):
        return "secret_denylist"
    if any(name.endswith(suffix) for suffix in _SECRET_FILE_SUFFIXES):
        return "secret_denylist"
    return None


def _matching_exclusion(relpath: str, excluded_by_path: Mapping[str, ManifestEntry]) -> ManifestEntry | None:
    path = Path(relpath)
    candidates = [path.as_posix()]
    parts = path.parts
    for index in range(1, len(parts)):
        candidates.append(Path(*parts[:index]).as_posix())
    for candidate in candidates:
        entry = excluded_by_path.get(candidate)
        if entry is not None:
            return entry
    return None


def _safe_token(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or value.startswith(".") or ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{label} must be a path-safe token")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    if any(char not in allowed for char in value):
        raise ValueError(f"{label} must be a path-safe token")
    return value


def _safe_visit_count(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("visit_count must be a positive integer")
    return value


def _safe_relpath(path: Path | str) -> str:
    path = Path(path)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"path '{path}' escapes workspace")
    return path.as_posix()


def _workspace_file(workspace: Path, relpath: str, *, must_exist: bool = True) -> Path:
    rel = _safe_relpath(Path(relpath))
    workspace = workspace.resolve()
    path = (workspace / rel).resolve()
    if not _is_within(path, workspace):
        raise ValueError(f"path '{relpath}' escapes workspace")
    if must_exist and not path.exists():
        raise FileNotFoundError(path)
    return path


def _relative_posix(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return ""
    if rel == Path("."):
        return ""
    return rel.as_posix()


def _join_rel(root: str, leaf: str) -> str:
    return leaf if not root else f"{root}/{leaf}"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_finite_score(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _hash_bytes(payload: bytes) -> str:
    return f"sha256:{sha256(payload).hexdigest()}"


def _stable_hash(payload: Any) -> str:
    return _hash_bytes(_canonical_json(_jsonable(payload)).encode("utf-8"))


def _canonical_json(payload: Any) -> str:
    return json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _jsonable(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {str(key): _jsonable(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [_jsonable(value) for value in payload]
    if isinstance(payload, Path):
        return payload.as_posix()
    if hasattr(payload, "__dict__"):
        return _jsonable(asdict(payload))
    return payload


def _replace_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent)) as handle:
        temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, dest)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
