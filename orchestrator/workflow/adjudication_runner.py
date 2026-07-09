"""Public adjudicated-provider runner façade."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from .adjudication import AdjudicationDeadline, adjudication_visit_paths
from .adjudication_bindings import (
    AdjudicationBindings,
    AdjudicationExecution,
    AdjudicationRunnerBase,
)
from .adjudication_candidates import AdjudicationCandidatePhaseMixin
from .adjudication_finalization import AdjudicationFinalizationPhaseMixin
from .adjudication_helpers import AdjudicationHelpersMixin
from .adjudication_ledger import AdjudicationLedgerMixin
from .adjudication_resume import AdjudicationResumeMixin
from .adjudication_scoring import AdjudicationScoringMixin


class AdjudicationRunner(
    AdjudicationCandidatePhaseMixin,
    AdjudicationFinalizationPhaseMixin,
    AdjudicationHelpersMixin,
    AdjudicationLedgerMixin,
    AdjudicationResumeMixin,
    AdjudicationScoringMixin,
    AdjudicationRunnerBase,
):
    """Coordinate adjudication phases through an explicit bindings object."""

    def execute_adjudicated_provider_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a DSL 2.11 adjudicated provider step sequentially."""
        execution, preparation_error = self._prepare_adjudication_execution(
            step,
            context,
            state,
            runtime_step_id=runtime_step_id,
        )
        if preparation_error is not None:
            return preparation_error
        if execution is None:
            return self._adjudication_failure_result(
                "adjudication_resume_mismatch",
                "Missing adjudication execution context",
            )

        resume_error = self._reconcile_adjudication_resume(execution)
        if resume_error is not None:
            return resume_error
        baseline_error = self._ensure_adjudication_baseline(execution)
        if baseline_error is not None:
            return baseline_error
        candidate_error = self._execute_adjudication_candidates(execution)
        if candidate_error is not None:
            return candidate_error
        scoring_error = self._score_adjudication_candidates(execution)
        if scoring_error is not None:
            return scoring_error
        return self._finalize_adjudication(execution)

    def _prepare_adjudication_execution(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        runtime_step_id: Optional[str],
    ) -> tuple[Optional[AdjudicationExecution], Optional[Dict[str, Any]]]:
        """Resolve configuration, output paths, frame identity, and ledger path."""
        started = time.monotonic()
        deadline = AdjudicationDeadline(
            started_monotonic=started,
            timeout_sec=self._adjudication_timeout_value(step.get("timeout_sec")),
        )
        step_name = step.get("name", f"step_{self.current_step}")
        step_id = runtime_step_id or self._step_id(step)
        adjudicated = step.get("adjudicated_provider", {})
        if not isinstance(adjudicated, dict):
            return None, self._adjudication_failure_result(
                "adjudication_resume_mismatch",
                "Missing adjudicated_provider config",
            )

        resolved_expected_outputs, resolved_output_bundle, path_error = (
            self._resolve_output_contract_paths(step, state, context=context)
        )
        if path_error is not None:
            return None, path_error
        output_contract_step = dict(step)
        if resolved_expected_outputs is not None:
            output_contract_step["expected_outputs"] = resolved_expected_outputs
        if resolved_output_bundle is not None:
            if "variant_output" in step:
                output_contract_step["variant_output"] = resolved_output_bundle
            else:
                output_contract_step["output_bundle"] = resolved_output_bundle

        frame_context = self._adjudication_frame_context()
        run_root = frame_context["run_root"]
        frame_scope = frame_context["frame_scope"]
        step_visits = state.get("step_visits", {})
        visit_count = (
            step_visits.get(step_name, 1) if isinstance(step_visits, dict) else 1
        )
        visit_paths = adjudication_visit_paths(
            run_root,
            frame_scope,
            step_id,
            int(visit_count or 1),
        )

        adjudicated = dict(adjudicated)
        ledger_path_error = self._resolve_adjudication_score_ledger_path(
            adjudicated,
            state,
            context,
            step_name=step_name,
            visit_paths=visit_paths,
        )
        if ledger_path_error is not None:
            return None, ledger_path_error

        raw_candidates = adjudicated.get("candidates", [])
        raw_evaluator = adjudicated.get("evaluator", {})
        raw_selection = adjudicated.get("selection", {})
        return AdjudicationExecution(
            started=started,
            deadline=deadline,
            step=step,
            context=context,
            state=state,
            step_name=step_name,
            step_id=step_id,
            adjudicated=adjudicated,
            resolved_expected_outputs=resolved_expected_outputs,
            resolved_output_bundle=resolved_output_bundle,
            output_contract_step=output_contract_step,
            run_root=run_root,
            frame_scope=frame_scope,
            execution_frame_id=frame_context["execution_frame_id"],
            call_frame_id=frame_context["call_frame_id"],
            visit_count=visit_count,
            visit_paths=visit_paths,
            candidates_config=raw_candidates if isinstance(raw_candidates, list) else [],
            evaluator_config=raw_evaluator if isinstance(raw_evaluator, dict) else {},
            selection_config=raw_selection if isinstance(raw_selection, dict) else {},
        ), None

    def _ensure_adjudication_baseline(
        self,
        execution: AdjudicationExecution,
    ) -> Optional[Dict[str, Any]]:
        """Create the baseline if needed and finish candidate-phase policy."""
        required_surfaces = self._adjudication_required_path_surfaces(
            execution.output_contract_step
        )
        optional_surfaces = self._adjudication_optional_path_surfaces(
            execution.output_contract_step
        )
        if execution.baseline_manifest is None:
            try:
                execution.deadline.require_time_remaining("baseline snapshot")
                execution.baseline_manifest = self._bindings.create_baseline_snapshot(
                    parent_workspace=self.workspace,
                    run_root=execution.run_root,
                    visit_paths=execution.visit_paths,
                    workflow_checksum=execution.state.get("workflow_checksum", ""),
                    resolved_consumes=execution.state.get("_resolved_consumes", {}),
                    required_path_surfaces=required_surfaces,
                    optional_path_surfaces=optional_surfaces,
                )
            except TimeoutError as exc:
                return self._adjudication_failure_result(
                    "timeout",
                    str(exc),
                    visit_paths=execution.visit_paths,
                )
            except Exception as exc:
                return self._adjudication_failure_result(
                    getattr(exc, "failure_type", "adjudication_resume_mismatch"),
                    str(exc),
                )

        execution.require_single_score = bool(
            execution.selection_config.get("require_score_for_single_candidate") is True
        )
        execution.retry_policy = self._adjudication_retry_policy(execution.step)
        if execution.resume_loaded:
            resume_state = execution.resume_state or {}
            execution.candidate_configs_to_run = resume_state.get(
                "pending_candidate_configs", []
            )
        else:
            execution.candidate_configs_to_run = list(
                enumerate(execution.candidates_config)
            )
        return None


__all__ = ["AdjudicationBindings", "AdjudicationRunner"]
