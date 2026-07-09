"""Scorer resolution and candidate evaluation for adjudication."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..exec.retry import RetryPolicy
from ..providers.types import ProviderParams
from .adjudication import (
    AdjudicationDeadline,
    AdjudicationVisitPaths,
    EVALUATION_PACKET_SCHEMA,
    EvaluatorOutputError,
    EvidencePacketError,
    SECRET_DETECTION_POLICY,
    build_evaluation_packet,
    candidate_paths,
    parse_evaluator_output,
    persist_scorer_resolution_failure,
    persist_scorer_snapshot,
    scorer_identity_hash,
)
from .adjudication_bindings import AdjudicationExecution
from .adjudication_prompt_evidence import adjudication_consumed_artifacts_for_prompt
from .adjudication_runtime import AdjudicationRuntime
from .executor_runtime import RuntimeStepInput




class AdjudicationScoringMixin:
    def _score_adjudication_candidates(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
    ) -> Optional[Dict[str, Any]]:
        """Resolve the scorer and evaluate all output-valid candidates."""
        candidates = execution.candidates
        scorer = execution.scorer
        scorer_failure = execution.scorer_failure
        evaluator_prompt = execution.evaluator_prompt
        evaluator_config = execution.evaluator_config
        context = execution.context
        state = execution.state
        visit_paths = execution.visit_paths
        step = execution.step
        output_contract_step = execution.output_contract_step
        run_root = execution.run_root
        frame_scope = execution.frame_scope
        step_id = execution.step_id
        visit_count = execution.visit_count
        deadline = execution.deadline
        retry_policy = execution.retry_policy
        if retry_policy is None:
            raise RuntimeError(
                "adjudication retry policy must be initialized before candidate scoring"
            )
        output_valid = [
            candidate
            for candidate in candidates
            if candidate.get("candidate_status") == "output_valid"
        ]
        score_pending = [
            candidate
            for candidate in output_valid
            if candidate.get("score_status") not in {"scored", "evaluation_failed", "scorer_unavailable"}
        ]
        if score_pending and scorer is None and scorer_failure is None:
            scorer, evaluator_prompt, scorer_failure = self._resolve_adjudication_scorer(
                evaluator_config if isinstance(evaluator_config, dict) else {},
                context,
                state,
                visit_paths=visit_paths,
            )
        if scorer_failure is not None:
            for candidate in score_pending:
                candidate.update(
                    {
                        "score_status": "scorer_unavailable",
                        "scorer_resolution_failure_key": scorer_failure["scorer_resolution_failure_key"],
                        "failure_type": scorer_failure["failure_type"],
                        "failure_message": scorer_failure["failure_message"],
                    }
                )
        elif scorer is not None:
            for candidate in score_pending:
                try:
                    self._score_adjudicated_candidate(
                        candidate=candidate,
                        scorer=scorer,
                        evaluator_prompt=evaluator_prompt,
                        evaluator_config=evaluator_config if isinstance(evaluator_config, dict) else {},
                        step=step,
                        output_contract_step=output_contract_step,
                        run_root=run_root,
                        frame_scope=frame_scope,
                        step_id=step_id,
                        visit_count=int(visit_count or 1),
                        context=context,
                        state=state,
                        deadline=deadline,
                        retry_policy=retry_policy,
                    )
                except TimeoutError as exc:
                    return self._adjudication_failure_result(
                        "timeout",
                        str(exc),
                        candidates=candidates,
                        visit_paths=visit_paths,
                    )
        if score_pending:
            self._persist_adjudication_candidates(
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                candidates=candidates,
            )
        execution.scorer = scorer
        execution.evaluator_prompt = evaluator_prompt
        execution.scorer_failure = scorer_failure
        return None

    def _adjudication_consumed_artifacts_for_prompt(
        self: AdjudicationRuntime,
        step: RuntimeStepInput,
        state: Dict[str, Any],
        *,
        step_name: str,
        consume_identity: str,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        return adjudication_consumed_artifacts_for_prompt(
            step,
            state,
            step_name=step_name,
            consume_identity=consume_identity,
            uses_qualified_identities=self._uses_qualified_identities,
            workflow_artifacts=self.workflow_artifacts,
            private_workflow_artifacts=self.private_workflow_artifacts,
        )

    def _resolve_adjudication_scorer(
            self: AdjudicationRuntime,
            evaluator_config: Mapping[str, Any],
            context: Dict[str, Any],
            state: Dict[str, Any],
            *,
        visit_paths: AdjudicationVisitPaths,
            persist: bool = True,
        ) -> tuple[Optional[dict[str, Any]], str, Optional[dict[str, Any]]]:
            limits = dict(evaluator_config.get("evidence_limits") or {})
            limits.setdefault("max_item_bytes", 262144)
            limits.setdefault("max_packet_bytes", 1048576)
            evaluator_prompt_source_kind = (
                "asset_file" if "asset_file" in evaluator_config else "input_file"
            )
            evaluator_prompt_source = evaluator_config.get("asset_file") or evaluator_config.get("input_file")
            rubric_source_kind = None
            rubric_source = None
            if "rubric_asset_file" in evaluator_config:
                rubric_source_kind = "asset_file"
                rubric_source = evaluator_config.get("rubric_asset_file")
            elif "rubric_input_file" in evaluator_config:
                rubric_source_kind = "input_file"
                rubric_source = evaluator_config.get("rubric_input_file")

            def scorer_failure(failure_type: str, failure_message: str) -> dict[str, Any]:
                payload = {
                    "failure_type": failure_type,
                    "failure_message": failure_message,
                    "evaluator_provider": evaluator_config.get("provider"),
                    "evaluator_params": evaluator_config.get("provider_params", {}),
                    "evaluator_prompt_source_kind": evaluator_prompt_source_kind,
                    "evaluator_prompt_source": evaluator_prompt_source,
                    "rubric_source_kind": rubric_source_kind,
                    "rubric_source": rubric_source,
                    "evaluator_json_contract": "adjudication.evaluator_json.v1",
                    "evaluation_packet_schema": EVALUATION_PACKET_SCHEMA,
                    "evidence_limits": limits,
                    "evidence_confidentiality": evaluator_config.get("evidence_confidentiality"),
                    "secret_detection_policy": SECRET_DETECTION_POLICY,
                }
                payload["scorer_resolution_failure_key"] = self._stable_runtime_hash(
                    {
                        key: value
                        for key, value in payload.items()
                        if key not in {"failure_message", "scorer_resolution_failure_key"}
                    }
                )
                if persist:
                    persist_scorer_resolution_failure(payload, visit_paths.scorer_root)
                return payload

            provider_name = evaluator_config.get("provider")
            if not isinstance(provider_name, str) or not provider_name:
                return None, "", scorer_failure(
                    "missing_evaluator_provider",
                    "evaluator provider is missing",
                )
            if not self.provider_registry.exists(provider_name):
                return None, "", scorer_failure(
                    "evaluator_provider_not_found",
                    f"evaluator provider '{provider_name}' is not registered",
                )

            if (
                evaluator_prompt_source_kind == "input_file"
                and isinstance(evaluator_prompt_source, str)
                and not (self.workspace / evaluator_prompt_source).exists()
            ):
                return None, "", scorer_failure(
                    "evaluator_prompt_read_failed",
                    f"evaluator input file '{evaluator_prompt_source}' does not exist",
                )

            try:
                evaluator_prompt, prompt_error = self.prompt_composer.read_prompt_source(
                    dict(evaluator_config),
                    step_name="adjudication_evaluator",
                    contract_violation_result=self._contract_violation_result,
                )
            except OSError as exc:
                return None, "", scorer_failure("evaluator_prompt_read_failed", str(exc))
            if prompt_error is not None:
                return None, "", scorer_failure(
                    prompt_error.get("error", {}).get("type", "scorer_unavailable"),
                    prompt_error.get("error", {}).get("message", "scorer prompt unavailable"),
                )
            rubric_content = None
            rubric_hash = None
            if rubric_source_kind is not None and isinstance(rubric_source, str):
                if rubric_source_kind == "input_file" and not (self.workspace / rubric_source).exists():
                    return None, "", scorer_failure(
                        "rubric_read_failed",
                        f"rubric input file '{rubric_source}' does not exist",
                    )
                rubric_step = {rubric_source_kind: rubric_source}
                try:
                    rubric_content, rubric_error = self.prompt_composer.read_prompt_source(
                        rubric_step,
                        step_name="adjudication_evaluator_rubric",
                        contract_violation_result=self._contract_violation_result,
                    )
                except OSError as exc:
                    return None, "", scorer_failure("rubric_read_failed", str(exc))
                if rubric_error is not None:
                    return None, "", scorer_failure(
                        rubric_error.get("error", {}).get("type", "rubric_read_failed"),
                        rubric_error.get("error", {}).get("message", "rubric unavailable"),
                    )
                rubric_hash = self._text_hash(rubric_content)
            provider_context = self._create_provider_context(context, state)
            merged_params = self.provider_registry.merge_params(
                provider_name,
                evaluator_config.get("provider_params", {}),
            )
            try:
                substituted_params, param_errors = self._substitute_provider_params(
                    merged_params,
                    provider_context,
                )
            except Exception as exc:
                param_errors = [str(exc)]
                substituted_params = {}
            if param_errors:
                return None, "", scorer_failure(
                    "evaluator_params_substitution_failed",
                    "; ".join(str(error) for error in param_errors),
                )
            scorer = {
                "evaluator_provider": provider_name,
                "evaluator_model": self._provider_model(substituted_params),
                "evaluator_params": substituted_params,
                "evaluator_params_hash": self._stable_runtime_hash(substituted_params),
                "evaluator_config_hash": self._stable_runtime_hash(evaluator_config),
                "evaluator_prompt_source_kind": evaluator_prompt_source_kind,
                "evaluator_prompt_source": evaluator_prompt_source,
                "evaluator_prompt_content": evaluator_prompt,
                "evaluator_prompt_hash": self._text_hash(evaluator_prompt),
                "rubric_source_kind": rubric_source_kind,
                "rubric_source": rubric_source,
                "rubric_content": rubric_content,
                "rubric_hash": rubric_hash,
                "evidence_confidentiality": evaluator_config.get("evidence_confidentiality"),
                "secret_detection_policy": SECRET_DETECTION_POLICY,
                "evaluation_packet_schema": EVALUATION_PACKET_SCHEMA,
                "evidence_limits": limits,
            }
            scorer["scorer_identity_hash"] = scorer_identity_hash(scorer)
            if persist:
                persist_scorer_snapshot(scorer, visit_paths.scorer_root)
            return scorer, evaluator_prompt, None

    def _score_adjudicated_candidate(
            self: AdjudicationRuntime,
            *,
            candidate: dict[str, Any],
            scorer: dict[str, Any],
            evaluator_prompt: str,
            evaluator_config: Mapping[str, Any],
            step: RuntimeStepInput,
            output_contract_step: Dict[str, Any],
            run_root: Path,
            frame_scope: str,
            step_id: str,
            visit_count: int,
            context: Dict[str, Any],
            state: Dict[str, Any],
            deadline: AdjudicationDeadline,
            retry_policy: RetryPolicy,
        ) -> None:
            paths = candidate_paths(
                run_root,
                frame_scope,
                step_id,
                visit_count,
                str(candidate["candidate_id"]),
            )
            candidate.update(
                {
                    "scorer_identity_hash": scorer.get("scorer_identity_hash"),
                    "evaluator_provider": scorer.get("evaluator_provider"),
                    "evaluator_model": scorer.get("evaluator_model"),
                    "evaluator_params_hash": scorer.get("evaluator_params_hash"),
                    "evaluator_config_hash": scorer.get("evaluator_config_hash"),
                    "evaluator_prompt_source_kind": scorer.get("evaluator_prompt_source_kind"),
                    "evaluator_prompt_source": scorer.get("evaluator_prompt_source"),
                    "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash"),
                    "evidence_confidentiality": scorer.get("evidence_confidentiality"),
                    "secret_detection_policy": scorer.get("secret_detection_policy"),
                    "rubric_source_kind": scorer.get("rubric_source_kind"),
                    "rubric_source": scorer.get("rubric_source"),
                    "rubric_hash": scorer.get("rubric_hash"),
                }
            )
            try:
                consumed_artifacts, consumed_relpath_targets = self._adjudication_consumed_artifacts_for_prompt(
                    step,
                    state,
                    step_name=str(step.get("name", "")),
                    consume_identity=step_id,
                )
                packet = build_evaluation_packet(
                    candidate_id=str(candidate["candidate_id"]),
                    candidate_workspace=paths.workspace,
                    rendered_prompt=paths.prompt_path.read_text(encoding="utf-8"),
                    expected_outputs=output_contract_step.get("expected_outputs"),
                    output_bundle=output_contract_step.get("output_bundle"),
                    artifacts=candidate.get("artifacts", {}),
                    scorer=scorer,
                    evidence_limits=scorer.get("evidence_limits"),
                    workflow_secret_values=self._workflow_secret_values(step),
                    rubric_content=scorer.get("rubric_content") if isinstance(scorer.get("rubric_content"), str) else None,
                    consumed_artifacts=consumed_artifacts,
                    consumed_relpath_targets=consumed_relpath_targets,
                    candidate_metadata={
                        "candidate_provider": candidate.get("candidate_provider"),
                        "candidate_model": candidate.get("candidate_model"),
                        "candidate_params_hash": candidate.get("candidate_params_hash"),
                        "candidate_index": candidate.get("candidate_index"),
                        "prompt_variant_id": candidate.get("prompt_variant_id"),
                    },
                    prompt_metadata={
                        "prompt_source_kind": candidate.get("prompt_source_kind"),
                        "prompt_source": candidate.get("prompt_source"),
                        "composed_prompt_hash": candidate.get("composed_prompt_hash"),
                    },
                )
                paths.evaluation_packet_path.parent.mkdir(parents=True, exist_ok=True)
                paths.evaluation_packet_path.write_text(
                    json.dumps(packet, sort_keys=True, ensure_ascii=False),
                    encoding="utf-8",
                )
                candidate["evaluation_packet_hash"] = packet["evaluation_packet_hash"]
            except (EvidencePacketError, OSError, ValueError) as exc:
                candidate.update(
                    {
                        "score_status": "evaluation_failed",
                        "failure_type": getattr(exc, "failure_type", "evidence_packet_failed"),
                        "failure_message": str(exc),
                    }
                )
                return

            evaluator_prompt_text = (
                f"{evaluator_prompt}\n\nEvaluator Packet:"
                f"{json.dumps(packet, sort_keys=True, ensure_ascii=False)}"
            )
            paths.evaluator_workspace.mkdir(parents=True, exist_ok=True)
            candidate["evaluator_attempts"] = []
            attempt = 0
            while True:
                deadline.require_time_remaining(
                    f"candidate {candidate['candidate_id']} evaluator attempt"
                )
                invocation, error = self._prepare_provider_invocation(
                    provider_name=str(evaluator_config.get("provider")),
                    params=ProviderParams(
                        params=evaluator_config.get("provider_params", {}),
                        input_file=evaluator_config.get("input_file"),
                        output_file=None,
                    ),
                    context=self._create_provider_context(context, state),
                    prompt_content=evaluator_prompt_text,
                    env=step.get("env"),
                    secrets=step.get("secrets"),
                    timeout_sec=deadline.remaining_timeout_sec(),
                )
                if error or invocation is None:
                    candidate.update(
                        {
                            "score_status": "evaluation_failed",
                            "failure_type": (error or {}).get("type", "evaluator_preparation_failed"),
                            "failure_message": (error or {}).get("message", "evaluator preparation failed"),
                        }
                    )
                    return
                exec_result = self._execute_provider_invocation(
                    invocation,
                    cwd=paths.evaluator_workspace,
                )
                paths.evaluation_output_path.write_bytes(exec_result.stdout)
                paths.evaluation_stderr_log.write_bytes(exec_result.stderr)
                candidate["evaluator_attempt_count"] = attempt + 1
                candidate["evaluator_attempts"].append(
                    {
                        "attempt": attempt + 1,
                        "exit_code": exec_result.exit_code,
                        "duration_ms": exec_result.duration_ms,
                    }
                )
                if exec_result.exit_code == 0:
                    break
                if retry_policy.should_retry(exec_result.exit_code, attempt):
                    self._wait_for_adjudication_retry(retry_policy, deadline)
                    attempt += 1
                    continue
                candidate.update(
                    {
                        "score_status": "evaluation_failed",
                        "failure_type": "timeout" if exec_result.exit_code == 124 else "evaluator_failed",
                        "failure_message": "evaluator provider failed",
                    }
                )
                if exec_result.exit_code == 124 and self._adjudication_deadline_expired(deadline):
                    raise TimeoutError(
                        "adjudicated provider deadline expired during evaluator execution"
                    )
                return
            try:
                parsed = parse_evaluator_output(
                    exec_result.stdout,
                    expected_candidate_id=str(candidate["candidate_id"]),
                )
            except EvaluatorOutputError as exc:
                candidate.update(
                    {
                        "score_status": "evaluation_failed",
                        "failure_type": "invalid_evaluator_json",
                        "failure_message": str(exc),
                    }
                )
                return
            candidate.update(
                {
                    "score_status": "scored",
                    "score": parsed["score"],
                    "summary": parsed["summary"],
                }
            )

    def _resolve_provider_params_for_adjudication(
            self: AdjudicationRuntime,
            provider_name: str,
            params: Any,
            context: Dict[str, Any],
            state: Dict[str, Any],
        ) -> tuple[dict[str, Any], list[str]]:
            raw_params = params if isinstance(params, dict) else {}
            merged = self.provider_registry.merge_params(provider_name, raw_params)
            provider_context = self._create_provider_context(context, state)
            try:
                substituted, errors = self._substitute_provider_params(
                    merged,
                    provider_context,
                )
            except Exception as exc:
                return merged, [str(exc)]
            return substituted, [str(error) for error in errors]
