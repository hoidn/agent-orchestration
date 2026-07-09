"""Selection, promotion, and terminal validation phase for adjudication."""

from __future__ import annotations

import time
from typing import Any, Dict

from ..contracts.output_contract import OutputContractError, validate_output_bundle
from .adjudication import PromotionConflictError, candidate_paths
from .adjudication_bindings import AdjudicationExecution, AdjudicationSelection
from .adjudication_runtime import AdjudicationRuntime


class AdjudicationFinalizationPhaseMixin:
    def _finalize_adjudication(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
    ) -> Dict[str, Any]:
        """Select, promote, and validate through focused terminal phases."""
        selected = self._select_adjudication_candidate(execution)
        if isinstance(selected, dict):
            return selected
        return self._promote_and_validate_adjudication(execution, selected)

    def _select_adjudication_candidate(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
    ) -> AdjudicationSelection | Dict[str, Any]:
        """Select a candidate and persist the pending-promotion ledger."""
        candidates = execution.candidates
        require_single_score = execution.require_single_score
        adjudicated = execution.adjudicated
        visit_paths = execution.visit_paths
        state = execution.state
        step_id = execution.step_id
        step_name = execution.step_name
        visit_count = execution.visit_count
        execution_frame_id = execution.execution_frame_id
        call_frame_id = execution.call_frame_id
        run_root = execution.run_root
        frame_scope = execution.frame_scope
        output_contract_step = execution.output_contract_step
        deadline = execution.deadline
        try:
            deadline.require_time_remaining("selection")
        except TimeoutError as exc:
            return self._adjudication_failure_result(
                "timeout", str(exc), candidates=candidates, visit_paths=visit_paths
            )
        selection = self._bindings.select_candidate(
            candidates,
            require_score_for_single_candidate=require_single_score,
        )
        if selection.error_type is not None:
            ledger_failure = self._write_adjudication_ledgers_failure(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=None,
                selection_reason="none",
                promotion_status="not_selected",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                preserve_primary_failure=True,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result(
                selection.error_type,
                selection.error_type,
                candidates=candidates,
                visit_paths=visit_paths,
            )
        selected = next(
            candidate
            for candidate in candidates
            if candidate["candidate_id"] == selection.selected_candidate_id
        )
        for candidate in candidates:
            candidate["selected"] = candidate["candidate_id"] == selection.selected_candidate_id
            if candidate["selected"]:
                candidate["promotion_status"] = "pending"
            else:
                candidate["promotion_status"] = "not_selected"
        self._persist_adjudication_candidates(
            run_root=run_root,
            frame_scope=frame_scope,
            step_id=step_id,
            visit_count=int(visit_count or 1),
            candidates=candidates,
        )
        selected_paths = candidate_paths(
            run_root,
            frame_scope,
            step_id,
            int(visit_count or 1),
            str(selection.selected_candidate_id),
        )
        ledger_path = adjudicated.get("score_ledger_path")
        try:
            deadline.require_time_remaining("ledger collision check")
        except TimeoutError as exc:
            return self._adjudication_failure_result(
                "timeout", str(exc), candidates=candidates, visit_paths=visit_paths
            )
        collision_message = self._adjudication_ledger_path_collision_message(
            adjudicated=adjudicated,
            output_contract_step=output_contract_step,
            candidates=candidates,
        )
        if collision_message is not None:
            selected["promotion_status"] = "failed"
            ledger_failure = self._write_adjudication_ledgers_failure(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=str(selection.selected_candidate_id),
                selection_reason=selection.selection_reason,
                promotion_status="failed",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                materialize_mirror=False,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result(
                "ledger_path_collision",
                collision_message,
                candidates=candidates,
                visit_paths=visit_paths,
            )
        try:
            deadline.require_time_remaining("pending ledger materialization")
            self._write_adjudication_ledgers(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=str(selection.selected_candidate_id),
                selection_reason=selection.selection_reason,
                promotion_status="pending",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                materialize_mirror=False,
            )
            self._persist_adjudication_candidates(
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                candidates=candidates,
            )
        except TimeoutError as exc:
            return self._adjudication_failure_result(
                "timeout", str(exc), candidates=candidates, visit_paths=visit_paths
            )
        except OSError as exc:
            return self._adjudication_failure_result(
                "ledger_mirror_failed",
                str(exc),
                candidates=candidates,
                visit_paths=visit_paths,
            )
        return AdjudicationSelection(
            selection=selection,
            selected=selected,
            selected_paths=selected_paths,
            ledger_path=ledger_path if isinstance(ledger_path, str) else None,
        )

    def _promote_and_validate_adjudication(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
        selected_state: AdjudicationSelection,
    ) -> Dict[str, Any]:
        """Promote the selected outputs, ledger them, and validate the parent."""
        candidates = execution.candidates
        adjudicated = execution.adjudicated
        visit_paths = execution.visit_paths
        state = execution.state
        step_id = execution.step_id
        step_name = execution.step_name
        visit_count = execution.visit_count
        execution_frame_id = execution.execution_frame_id
        call_frame_id = execution.call_frame_id
        run_root = execution.run_root
        frame_scope = execution.frame_scope
        resolved_expected_outputs = execution.resolved_expected_outputs
        resolved_output_bundle = execution.resolved_output_bundle
        baseline_manifest = execution.baseline_manifest
        if baseline_manifest is None:
            raise RuntimeError(
                "adjudication baseline must be initialized before promotion"
            )
        scorer = execution.scorer
        deadline = execution.deadline
        started = execution.started
        selection = selected_state.selection
        selected = selected_state.selected
        selected_paths = selected_state.selected_paths
        ledger_path = selected_state.ledger_path
        try:
            deadline.require_time_remaining("promotion")
            promotion = self._bindings.promote_candidate_outputs(
                expected_outputs=resolved_expected_outputs,
                output_bundle=resolved_output_bundle,
                candidate_workspace=selected_paths.workspace,
                parent_workspace=self.workspace,
                baseline_manifest=baseline_manifest,
                promotion_manifest_path=visit_paths.promotion_manifest_path,
                selected_candidate_id=str(selection.selected_candidate_id),
            )
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        except PromotionConflictError as exc:
            ledger_failure = self._write_adjudication_ledgers_failure(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=str(selection.selected_candidate_id),
                selection_reason=selection.selection_reason,
                promotion_status="failed",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                preserve_primary_failure=True,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result(
                getattr(exc, "failure_type", "promotion_conflict"),
                str(exc),
                candidates=candidates,
                visit_paths=visit_paths,
            )
        selected["promotion_status"] = "committed"
        selected["promoted_paths"] = promotion.promoted_paths
        self._persist_adjudication_candidates(
            run_root=run_root,
            frame_scope=frame_scope,
            step_id=step_id,
            visit_count=int(visit_count or 1),
            candidates=candidates,
        )
        try:
            deadline.require_time_remaining("terminal ledger materialization")
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        ledger_failure = self._write_adjudication_ledgers_failure(
            adjudicated=adjudicated,
            visit_paths=visit_paths,
            state=state,
            step_id=step_id,
            step_name=step_name,
            visit_count=int(visit_count or 1),
            candidates=candidates,
            selected_candidate_id=str(selection.selected_candidate_id),
            selection_reason=selection.selection_reason,
            promotion_status="committed",
            promoted_paths=promotion.promoted_paths,
            execution_frame_id=execution_frame_id,
            call_frame_id=call_frame_id,
        )
        if ledger_failure is not None:
            return ledger_failure
        try:
            deadline.require_time_remaining("parent output validation")
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        try:
            if resolved_output_bundle is not None:
                artifacts = validate_output_bundle(resolved_output_bundle, workspace=self.workspace)
            else:
                artifacts = self._bindings.validate_expected_outputs(
                    resolved_expected_outputs or [],
                    workspace=self.workspace,
                )
            deadline.require_time_remaining("parent output validation completion")
        except OutputContractError as exc:
            return self._adjudication_failure_result(
                "promotion_validation_failed",
                str(exc),
                candidates=candidates,
                visit_paths=visit_paths,
            )
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": duration_ms,
            "artifacts": artifacts,
            "adjudication": self._adjudication_state_block(
                selected_candidate_id=str(selection.selected_candidate_id),
                selected_score=selection.selected_score,
                selection_reason=selection.selection_reason,
                promotion_status="committed",
                scorer=scorer,
                score_ledger_path=ledger_path if isinstance(ledger_path, str) else None,
                run_score_ledger_path=visit_paths.run_score_ledger_path,
                scorer_snapshot_path=visit_paths.scorer_root / "metadata.json",
                promotion_manifest_path=visit_paths.promotion_manifest_path,
                candidates=candidates,
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
            ),
        }
