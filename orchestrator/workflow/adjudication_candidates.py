"""Candidate workspace and provider execution phase for adjudication."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..contracts.output_contract import OutputContractError, validate_output_bundle
from ..providers.types import ProviderParams
from .adjudication import candidate_paths
from .adjudication_bindings import AdjudicationExecution
from .adjudication_runtime import AdjudicationRuntime


class AdjudicationCandidatePhaseMixin:
    def _execute_adjudication_candidates(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
    ) -> Optional[Dict[str, Any]]:
        """Run all pending isolated candidate providers."""
        for index, candidate_config in execution.candidate_configs_to_run:
            if not isinstance(candidate_config, dict):
                continue
            failure = self._execute_single_adjudication_candidate(
                execution,
                index=index,
                candidate_config=candidate_config,
            )
            if failure is not None:
                return failure
        return None

    def _execute_single_adjudication_candidate(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
        *,
        index: int,
        candidate_config: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Run and persist one isolated candidate."""
        step = execution.step
        context = execution.context
        state = execution.state
        run_root = execution.run_root
        frame_scope = execution.frame_scope
        step_id = execution.step_id
        visit_count = execution.visit_count
        visit_paths = execution.visit_paths
        output_contract_step = execution.output_contract_step
        resolved_expected_outputs = execution.resolved_expected_outputs
        resolved_output_bundle = execution.resolved_output_bundle
        candidates = execution.candidates
        retry_policy = execution.retry_policy
        if retry_policy is None:
            raise RuntimeError(
                "adjudication retry policy must be initialized before candidate execution"
            )
        deadline = execution.deadline
        candidate_id = str(candidate_config.get("id"))
        candidate_provider = str(candidate_config.get("provider"))
        paths = candidate_paths(run_root, frame_scope, step_id, int(visit_count or 1), candidate_id)
        candidate_step = self._candidate_step_from_adjudicated_step(step, candidate_config)
        candidate_params, _candidate_param_errors = self._resolve_provider_params_for_adjudication(
            candidate_provider,
            candidate_config.get("provider_params", {}),
            context,
            state,
        )
        prompt_source_kind, prompt_source = self._prompt_source_metadata(candidate_step)
        candidate_record = {
            "candidate_id": candidate_id,
            "candidate_index": index,
            "candidate_provider": candidate_provider,
            "candidate_model": self._provider_model(candidate_params),
            "candidate_params_hash": self._stable_runtime_hash(candidate_params),
            "candidate_config_hash": self._stable_runtime_hash(candidate_config),
            "prompt_variant_id": candidate_config.get("prompt_variant_id"),
            "prompt_source_kind": prompt_source_kind,
            "prompt_source": prompt_source,
            "candidate_root": paths.candidate_root.relative_to(self.workspace).as_posix()
            if self._path_under(paths.candidate_root, self.workspace)
            else paths.candidate_root.as_posix(),
            "candidate_workspace": paths.workspace.relative_to(self.workspace).as_posix()
            if self._path_under(paths.workspace, self.workspace)
            else paths.workspace.as_posix(),
            "attempt_count": 0,
            "provider_attempts": [],
            "output_paths": {},
        }
        attempt = 0
        try:
            while True:
                deadline.require_time_remaining(f"candidate {candidate_id} provider attempt")
                self._bindings.prepare_candidate_workspace_from_baseline(
                    baseline_workspace=visit_paths.baseline_workspace,
                    candidate_workspace=paths.workspace,
                )
                deadline.require_time_remaining(f"candidate {candidate_id} workspace copy")
                prompt, prompt_error = self._compose_provider_prompt_for_step(
                    candidate_step,
                    context,
                    state,
                    workspace=paths.workspace,
                    output_contract_step=output_contract_step,
                    runtime_step_id=step_id,
                )
                if prompt_error is not None:
                    candidate_record.update(
                        {
                            "candidate_status": "prompt_failed",
                            "score_status": "not_evaluated",
                            "provider_exit_code": None,
                            "failure_type": prompt_error.get("error", {}).get("type", "prompt_failed"),
                            "failure_message": prompt_error.get("error", {}).get("message", "prompt failed"),
                        }
                    )
                    break
                paths.prompt_path.parent.mkdir(parents=True, exist_ok=True)
                paths.prompt_path.write_text(prompt or "", encoding="utf-8")
                candidate_record["composed_prompt_hash"] = self._text_hash(prompt or "")
                if not candidate_record.get("prompt_variant_id"):
                    candidate_record["prompt_variant_id"] = self._stable_runtime_hash(
                        {
                            "prompt_source_kind": prompt_source_kind,
                            "prompt_source": prompt_source,
                            "composed_prompt_hash": candidate_record["composed_prompt_hash"],
                        }
                    )

                invocation, error = self._prepare_provider_invocation(
                    provider_name=candidate_provider,
                    params=ProviderParams(
                        params=candidate_config.get("provider_params", {}),
                        input_file=candidate_step.get("input_file"),
                        output_file=None,
                    ),
                    context=self._create_provider_context(context, state),
                    prompt_content=prompt,
                    env=self._provider_env_with_runtime_output_bundle_path(
                        candidate_step,
                        resolved_output_bundle,
                    ),
                    secrets=candidate_step.get("secrets"),
                    timeout_sec=deadline.remaining_timeout_sec(),
                )
                if error or invocation is None:
                    candidate_record.update(
                        {
                            "candidate_status": "prompt_failed",
                            "score_status": "not_evaluated",
                            "provider_exit_code": None,
                            "failure_type": (error or {}).get("type", "provider_preparation_failed"),
                            "failure_message": (error or {}).get("message", "provider preparation failed"),
                        }
                    )
                    break
                exec_result = self._execute_provider_invocation(invocation, cwd=paths.workspace)
                paths.stdout_log.write_bytes(exec_result.stdout)
                paths.stderr_log.write_bytes(exec_result.stderr)
                candidate_record["provider_exit_code"] = exec_result.exit_code
                candidate_record["attempt_count"] = attempt + 1
                candidate_record["provider_attempts"].append(
                    {
                        "attempt": attempt + 1,
                        "exit_code": exec_result.exit_code,
                        "duration_ms": exec_result.duration_ms,
                    }
                )
                if exec_result.exit_code != 0:
                    if retry_policy.should_retry(exec_result.exit_code, attempt):
                        self._wait_for_adjudication_retry(retry_policy, deadline)
                        attempt += 1
                        continue
                    candidate_record.update(
                        {
                            "candidate_status": "timeout" if exec_result.exit_code == 124 else "provider_failed",
                            "score_status": "not_evaluated",
                            "failure_type": "timeout" if exec_result.exit_code == 124 else "provider_failed",
                            "failure_message": "candidate provider failed",
                        }
                    )
                    if exec_result.exit_code == 124 and self._adjudication_deadline_expired(deadline):
                        candidates.append(candidate_record)
                        self._persist_adjudication_candidates(
                            run_root=run_root,
                            frame_scope=frame_scope,
                            step_id=step_id,
                            visit_count=int(visit_count or 1),
                            candidates=candidates,
                        )
                        return self._adjudication_failure_result(
                            "timeout",
                            "adjudicated provider deadline expired during candidate provider execution",
                            candidates=candidates,
                            visit_paths=visit_paths,
                        )
                    break
                try:
                    if resolved_output_bundle is not None:
                        artifacts = validate_output_bundle(resolved_output_bundle, workspace=paths.workspace)
                    else:
                        artifacts = self._bindings.validate_expected_outputs(
                            resolved_expected_outputs or [],
                            workspace=paths.workspace,
                        )
                except OutputContractError as exc:
                    candidate_record.update(
                        {
                            "candidate_status": "contract_failed",
                            "score_status": "not_evaluated",
                            "failure_type": "contract_failed",
                            "failure_message": str(exc),
                        }
                    )
                    break
                candidate_record.update(
                    {
                        "candidate_status": "output_valid",
                        "score_status": "not_evaluated",
                        "artifacts": artifacts,
                        "output_paths": self._output_paths_from_contract(output_contract_step),
                    }
                )
                break
        except TimeoutError as exc:
            candidate_record.update(
                {
                    "candidate_status": "timeout",
                    "score_status": "not_evaluated",
                    "provider_exit_code": 124,
                    "failure_type": "timeout",
                    "failure_message": str(exc),
                }
            )
            candidates.append(candidate_record)
            self._persist_adjudication_candidates(
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                candidates=candidates,
            )
            return self._adjudication_failure_result(
                "timeout",
                str(exc),
                candidates=candidates,
                visit_paths=visit_paths,
            )
        except Exception as exc:
            candidate_record.update(
                {
                    "candidate_status": "prompt_failed",
                    "score_status": "not_evaluated",
                    "provider_exit_code": None,
                    "failure_type": getattr(exc, "failure_type", "candidate_failed"),
                    "failure_message": str(exc),
                }
            )
        candidates.append(candidate_record)
        self._persist_adjudication_candidates(
            run_root=run_root,
            frame_scope=frame_scope,
            step_id=step_id,
            visit_count=int(visit_count or 1),
            candidates=[candidate_record],
        )
        return None
