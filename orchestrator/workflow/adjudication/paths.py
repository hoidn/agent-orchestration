"""Deterministic sidecar paths for adjudicated-provider visits and candidates."""

from __future__ import annotations

from pathlib import Path

from .models import AdjudicationVisitPaths, CandidateRuntimePaths
from .utils import _safe_token, _safe_visit_count


def adjudication_cleanup_guard_path(
    run_root: Path,
    frame_scope: str,
    step_id: str,
) -> Path:
    """Return the run-owned cleanup guard for one adjudicated step."""

    frame = _safe_token(frame_scope, "frame_scope")
    step = _safe_token(step_id, "step_id")
    return (
        run_root
        / "adjudication-cleanup-guards"
        / frame
        / step
        / "guard.json"
    )


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
    candidate_root = candidate_visit_root(
        run_root,
        frame_scope,
        step_id,
        visit_count,
    ) / _safe_token(candidate_id, "candidate_id")
    return CandidateRuntimePaths(
        candidate_root=candidate_root,
        workspace=candidate_root / "workspace",
        stdout_log=candidate_root / "stdout.log",
        stderr_log=candidate_root / "stderr.log",
        prompt_path=candidate_root / "prompt.txt",
        evaluation_packet_path=candidate_root / "evaluation_packet.json",
        evaluation_output_path=candidate_root / "evaluation_output.json",
        evaluation_stderr_log=candidate_root / "evaluation_stderr.log",
        evaluator_workspace=candidate_root / "evaluator" / "workspace",
    )


def candidate_visit_root(
    run_root: Path,
    frame_scope: str,
    step_id: str,
    visit_count: int,
) -> Path:
    frame = _safe_token(frame_scope, "frame_scope")
    step = _safe_token(step_id, "step_id")
    visit = _safe_visit_count(visit_count)
    return run_root / "candidates" / frame / step / str(visit)


def candidate_metadata_path(paths: CandidateRuntimePaths) -> Path:
    return paths.candidate_root / "metadata.json"
