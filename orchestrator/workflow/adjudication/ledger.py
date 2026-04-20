"""Score ledger row generation and materialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import SCORE_ROW_SCHEMA, LedgerConflictError
from .utils import _atomic_write_text, _canonical_json, _stable_hash, _utc_now

def load_score_ledger_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        document = json.loads(line)
        if not isinstance(document, dict):
            raise ValueError(f"score ledger row {line_number} must be a JSON object")
        rows.append(document)
    return rows

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

def _ledger_owner(row: Mapping[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        row.get("row_schema"),
        row.get("run_id"),
        row.get("execution_frame_id"),
        row.get("step_id"),
        row.get("visit_count"),
    )
