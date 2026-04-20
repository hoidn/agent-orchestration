"""Scorer identity, evaluator JSON parsing, and candidate selection."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import (
    EVALUATION_PACKET_SCHEMA,
    EVALUATOR_JSON_CONTRACT,
    SECRET_DETECTION_POLICY,
    EvaluatorOutputError,
    SelectionResult,
)
from .utils import _atomic_write_text, _canonical_json, _is_finite_score, _stable_hash

def scorer_identity_hash(scorer: Mapping[str, Any]) -> str:
    return _stable_hash(
        {
            "evaluator_provider": scorer.get("evaluator_provider"),
            "evaluator_params": scorer.get("evaluator_params"),
            "evaluator_prompt_source_kind": scorer.get("evaluator_prompt_source_kind"),
            "evaluator_prompt_source": scorer.get("evaluator_prompt_source"),
            "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash"),
            "rubric_source_kind": scorer.get("rubric_source_kind"),
            "rubric_source": scorer.get("rubric_source"),
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
            reason = "highest_score" if require_score_for_single_candidate else "single_candidate_contract_valid"
            return SelectionResult(str(candidate["candidate_id"]), float(candidate["score"]), reason)
        if require_score_for_single_candidate:
            if candidate.get("score_status") == "scorer_unavailable":
                return SelectionResult(None, None, "none", "adjudication_scorer_unavailable")
            return SelectionResult(None, None, "none", "adjudication_partial_scoring_failed")
        return SelectionResult(str(candidate["candidate_id"]), None, "single_candidate_contract_valid")

    if any(candidate.get("score_status") == "scorer_unavailable" for candidate in valid):
        return SelectionResult(None, None, "none", "adjudication_scorer_unavailable")
    if any(candidate.get("score_status") != "scored" or not _is_finite_score(candidate.get("score")) for candidate in valid):
        return SelectionResult(None, None, "none", "adjudication_partial_scoring_failed")

    best_score = max(float(candidate["score"]) for candidate in valid)
    tied_best = [candidate for candidate in valid if float(candidate["score"]) == best_score]
    selected = tied_best[0]
    return SelectionResult(
        str(selected["candidate_id"]),
        best_score,
        "candidate_order_tie_break" if len(tied_best) > 1 else "highest_score",
    )

def _raise_invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")
