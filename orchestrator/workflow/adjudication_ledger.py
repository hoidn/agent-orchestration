"""Ledger, result, and promotion-path helpers for adjudication."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .adjudication import (
    AdjudicationVisitPaths,
    LedgerConflictError,
    SECRET_DETECTION_POLICY,
    adjudication_outcome,
    generate_score_ledger_rows,
)
from .adjudication_runtime import AdjudicationRuntime


class AdjudicationLedgerMixin:
    def _write_adjudication_ledgers(
            self: AdjudicationRuntime,
            *,
            adjudicated: Mapping[str, Any],
        visit_paths: AdjudicationVisitPaths,
            state: Dict[str, Any],
            step_id: str,
            step_name: str,
            visit_count: int,
            candidates: list[dict[str, Any]],
            selected_candidate_id: Optional[str],
            selection_reason: str,
            promotion_status: str,
            promoted_paths: Mapping[str, str],
            execution_frame_id: str,
            call_frame_id: Optional[str],
            materialize_mirror: bool = True,
        ) -> list[dict[str, Any]]:
            rows = generate_score_ledger_rows(
                run_id=str(state.get("run_id", self.state_manager.run_id)),
                workflow_file=str(state.get("workflow_file", "")),
                workflow_checksum=str(state.get("workflow_checksum", "")),
                dsl_version=self.workflow_version,
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                step_id=step_id,
                step_name=step_name,
                visit_count=visit_count,
                candidates=candidates,
                selected_candidate_id=selected_candidate_id,
                selection_reason=selection_reason,
                promotion_status=promotion_status,
                promoted_paths=promoted_paths,
            )
            rows_by_candidate = {str(row.get("candidate_id")): row for row in rows}
            for candidate in candidates:
                row = rows_by_candidate.get(str(candidate.get("candidate_id")))
                if row is not None:
                    candidate["candidate_run_key"] = row["candidate_run_key"]
                    candidate["score_run_key"] = row["score_run_key"]
            self._bindings.materialize_run_score_ledger(rows, visit_paths.run_score_ledger_path)
            mirror = adjudicated.get("score_ledger_path")
            if materialize_mirror and isinstance(mirror, str):
                self._bindings.materialize_score_ledger_mirror(rows, self.workspace / mirror)
            return rows

    def _write_adjudication_ledgers_failure(
            self: AdjudicationRuntime,
            *,
            adjudicated: Mapping[str, Any],
        visit_paths: AdjudicationVisitPaths,
            state: Dict[str, Any],
            step_id: str,
            step_name: str,
            visit_count: int,
            candidates: list[dict[str, Any]],
            selected_candidate_id: Optional[str],
            selection_reason: str,
            promotion_status: str,
            promoted_paths: Mapping[str, str],
            execution_frame_id: str,
            call_frame_id: Optional[str],
            preserve_primary_failure: bool = False,
            materialize_mirror: bool = True,
        ) -> Optional[Dict[str, Any]]:
            try:
                rows = self._write_adjudication_ledgers(
                    adjudicated=adjudicated,
                    visit_paths=visit_paths,
                    state=state,
                    step_id=step_id,
                    step_name=step_name,
                    visit_count=visit_count,
                    candidates=candidates,
                    selected_candidate_id=selected_candidate_id,
                    selection_reason=selection_reason,
                    promotion_status=promotion_status,
                    promoted_paths=promoted_paths,
                    execution_frame_id=execution_frame_id,
                    call_frame_id=call_frame_id,
                    materialize_mirror=False,
                )
            except OSError as exc:
                return self._adjudication_failure_result(
                    "ledger_mirror_failed",
                    str(exc),
                    candidates=candidates,
                    visit_paths=visit_paths,
                    selected_candidate_id=selected_candidate_id,
                    selection_reason=selection_reason,
                    promotion_status=promotion_status,
                )
            if materialize_mirror:
                mirror = adjudicated.get("score_ledger_path")
                if isinstance(mirror, str):
                    try:
                        self._bindings.materialize_score_ledger_mirror(rows, self.workspace / mirror)
                    except LedgerConflictError as exc:
                        return self._adjudication_failure_result(
                            "ledger_conflict",
                            str(exc),
                            candidates=candidates,
                            visit_paths=visit_paths,
                            selected_candidate_id=selected_candidate_id,
                            selection_reason=selection_reason,
                            promotion_status=promotion_status,
                        )
                    except OSError as exc:
                        if preserve_primary_failure:
                            return None
                        return self._adjudication_failure_result(
                            "ledger_mirror_failed",
                            str(exc),
                            candidates=candidates,
                            visit_paths=visit_paths,
                            selected_candidate_id=selected_candidate_id,
                            selection_reason=selection_reason,
                            promotion_status=promotion_status,
                        )
            return None

    def _adjudication_failure_result(
            self: AdjudicationRuntime,
            error_type: str,
            message: str,
            *,
            candidates: Optional[list[dict[str, Any]]] = None,
        visit_paths: Optional[AdjudicationVisitPaths] = None,
            selected_candidate_id: Optional[str] = None,
            selected_score: Optional[float] = None,
            selection_reason: Optional[str] = None,
            promotion_status: Optional[str] = None,
        ) -> Dict[str, Any]:
            mapped = adjudication_outcome(error_type)
            result = {
                "status": "failed",
                "exit_code": mapped["exit_code"],
                "duration_ms": 0,
                "error": {
                    "type": error_type,
                    "message": message,
                },
                "outcome": mapped["outcome"],
            }
            if candidates is not None or visit_paths is not None:
                if candidates:
                    selected_candidate = next(
                        (
                            candidate
                            for candidate in candidates
                            if candidate.get("selected")
                            or (
                                selected_candidate_id is not None
                                and str(candidate.get("candidate_id")) == selected_candidate_id
                            )
                        ),
                        None,
                    )
                    if selected_candidate is not None:
                        if selected_candidate_id is None:
                            selected_candidate_id = str(selected_candidate.get("candidate_id"))
                        if selected_score is None:
                            score = selected_candidate.get("score")
                            selected_score = float(score) if isinstance(score, (int, float)) else None
                        promotion_status = str(selected_candidate.get("promotion_status") or promotion_status or "failed")
                result["adjudication"] = {
                    "schema": "adjudicated_provider.state.v1",
                    "selected_candidate_id": selected_candidate_id,
                    "selected_score": selected_score,
                    "selection_reason": selection_reason or ("none" if selected_candidate_id is None else "highest_score"),
                    "promotion_status": promotion_status or ("not_selected" if selected_candidate_id is None else "failed"),
                    "run_score_ledger_path": (
                        visit_paths.run_score_ledger_path.as_posix()
                        if visit_paths is not None
                        else None
                    ),
                    "candidates": self._candidate_state_map(candidates or []),
                }
            return result

    def _adjudication_state_block(
            self: AdjudicationRuntime,
            *,
            selected_candidate_id: str,
            selected_score: Optional[float],
            selection_reason: str,
            promotion_status: str,
            scorer: Optional[Mapping[str, Any]],
            score_ledger_path: Optional[str],
            run_score_ledger_path: Path,
            scorer_snapshot_path: Path,
            promotion_manifest_path: Path,
            candidates: list[dict[str, Any]],
            execution_frame_id: str,
            call_frame_id: Optional[str],
        ) -> dict[str, Any]:
            return {
                "schema": "adjudicated_provider.state.v1",
                "execution_frame_id": execution_frame_id,
                "call_frame_id": call_frame_id,
                "selected_candidate_id": selected_candidate_id,
                "selected_score": selected_score,
                "selection_reason": selection_reason,
                "promotion_status": promotion_status,
                "scorer_identity_hash": scorer.get("scorer_identity_hash") if scorer else None,
                "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash") if scorer else None,
                "evidence_confidentiality": scorer.get("evidence_confidentiality") if scorer else None,
                "secret_detection_policy": SECRET_DETECTION_POLICY,
                "score_ledger_path": score_ledger_path,
                "run_score_ledger_path": run_score_ledger_path.as_posix(),
                "scorer_snapshot_path": scorer_snapshot_path.as_posix(),
                "promotion_manifest_path": promotion_manifest_path.as_posix(),
                "candidates": self._candidate_state_map(candidates),
            }

    def _adjudication_ledger_path_collision_message(
            self: AdjudicationRuntime,
            *,
            adjudicated: Mapping[str, Any],
            output_contract_step: Dict[str, Any],
            candidates: list[dict[str, Any]],
        ) -> Optional[str]:
            ledger_path = adjudicated.get("score_ledger_path")
            if not isinstance(ledger_path, str):
                return None
            ledger_abs = (self.workspace / ledger_path).resolve()
            dynamic_paths: set[Path] = set()
            for candidate in candidates:
                if candidate.get("candidate_status") != "output_valid":
                    continue
                artifacts = candidate.get("artifacts")
                if isinstance(artifacts, Mapping):
                    dynamic_paths.update(self._promotion_destination_paths(output_contract_step, artifacts))
            if ledger_abs in dynamic_paths:
                return "score ledger path collides with step-managed output path"
            return None
