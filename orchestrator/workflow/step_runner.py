"""Shared step dispatch for top-level and nested workflow execution."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..state import StepResult


class StepRunner:
    """Route one workflow step through shared execution and persistence helpers."""

    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def run_top_level(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        step_name: str,
        resume_current_step: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Execute one top-level step and persist its result when applicable."""
        if "for_each" in step:
            self.executor._execute_for_each(step, state, resume=resume_current_step)
            if step_name in state["steps"]:
                loop_results = state["steps"][step_name]
                if isinstance(loop_results, list):
                    self.executor.state_manager.update_loop_results(step_name, loop_results)
            result = state.get("steps", {}).get(step_name, {"status": "completed"})
            self.executor._emit_step_summary(step_name, step, result)
            return result

        if "repeat_until" in step:
            self.executor._execute_repeat_until(step, state, resume=resume_current_step)
            result = state.get("steps", {}).get(step_name, {"status": "completed"})
            self.executor._emit_step_summary(step_name, step, result)
            return result

        if "structured_if_branch" in step:
            result = self.executor._execute_structured_if_branch(step)
            return self.executor._persist_step_result(state, step_name, step, result)

        if "structured_if_join" in step:
            result = self.executor._execute_structured_if_join(step, state)
            return self.executor._persist_step_result(state, step_name, step, result)

        if "structured_match_case" in step:
            result = self.executor._execute_structured_match_case(step)
            return self.executor._persist_step_result(state, step_name, step, result)

        if "structured_match_join" in step:
            result = self.executor._execute_structured_match_join(step, state)
            return self.executor._persist_step_result(state, step_name, step, result)

        if "wait_for" in step:
            result = self.executor._execute_wait_for_result(step)
            phase_hint = None
            class_hint = None
            if result.get("timed_out"):
                phase_hint = "execution"
                class_hint = "timeout"
            elif isinstance(result.get("error"), dict) and result["error"].get("type") == "path_safety_error":
                phase_hint = "pre_execution"
                class_hint = "pre_execution_failed"
            return self.executor._persist_step_result(
                state,
                step_name,
                step,
                result,
                phase_hint=phase_hint,
                class_hint=class_hint,
                retryable_hint=False if class_hint == "pre_execution_failed" else None,
            )

        if "assert" in step:
            result = self.executor._execute_assert(step, state)
            return self.executor._persist_step_result(state, step_name, step, result)

        if "set_scalar" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self.executor._execute_set_scalar(step),
            )

        if "increment_scalar" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self.executor._execute_increment_scalar(step, state),
            )

        if "call" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self.executor._execute_call(step, state),
            )

        if "provider" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self.executor._execute_provider(step, state),
            )

        if "command" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self.executor._execute_command(step, state),
            )

        return None

    def run_nested(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        *,
        loop_name: str,
        iteration_index: int,
        nested_name: str,
        runtime_step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute one nested loop step and persist its iteration result."""
        scope = self.executor._build_loop_scope(state, iteration_state, parent_scope_steps)
        step_name_override = step.get("name")

        if "command" in step:
            result = self.executor._execute_command_with_context(step, context, state)
        elif "provider" in step:
            result = self.executor._execute_provider_with_context(
                step,
                context,
                state,
                runtime_step_id=runtime_step_id,
            )
        elif "assert" in step:
            result = self.executor._execute_assert(step, state, context=context, scope=scope)
        elif "set_scalar" in step:
            result = self.executor._execute_set_scalar(step)
        elif "increment_scalar" in step:
            result = self.executor._execute_increment_scalar(step, state)
        elif "wait_for" in step:
            result = self.executor._execute_wait_for_result(step)
        elif "structured_if_branch" in step:
            result = self.executor._execute_structured_if_branch(step)
        elif "structured_if_join" in step:
            result = self.executor._execute_structured_if_join(step, state, scope=scope)
        elif "structured_match_case" in step:
            result = self.executor._execute_structured_match_case(step)
        elif "structured_match_join" in step:
            result = self.executor._execute_structured_match_join(step, state, scope=scope)
        elif "call" in step:
            result = self.executor._execute_call(
                step,
                state,
                scope=scope,
                runtime_step_id=runtime_step_id,
                step_name_override=step_name_override,
            )
        else:
            result = {"status": "skipped", "exit_code": 0, "skipped": True}

        publish_error = self.executor._record_published_artifacts(
            step,
            nested_name,
            result,
            state,
            runtime_step_id=runtime_step_id,
        )
        if publish_error is not None:
            result = publish_error

        result.setdefault("name", nested_name)
        result.setdefault("step_id", runtime_step_id)
        result = self.executor._attach_outcome(step, result)
        iteration_state[nested_name] = result
        self.executor.state_manager.update_loop_step(
            loop_name,
            iteration_index,
            nested_name,
            self._to_step_result(result, nested_name),
        )
        return result

    def _execute_top_level_publish_and_persist(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        publish_error = self.executor._record_published_artifacts(step, step_name, result, state)
        if publish_error is not None:
            result = publish_error
        return self.executor._persist_step_result(state, step_name, step, result)

    @staticmethod
    def _to_step_result(result: Dict[str, Any], fallback_name: str) -> StepResult:
        """Convert a persisted result payload into the runtime StepResult model."""
        return StepResult(
            status=result.get("status", "completed" if result.get("exit_code", 0) == 0 else "failed"),
            name=result.get("name", fallback_name),
            step_id=result.get("step_id"),
            exit_code=result.get("exit_code", 0),
            duration_ms=result.get("duration_ms", 0),
            output=result.get("output"),
            lines=result.get("lines"),
            json=result.get("json"),
            error=result.get("error"),
            truncated=result.get("truncated", False),
            artifacts=result.get("artifacts"),
            skipped=result.get("skipped", False),
            files=result.get("files"),
            wait_duration_ms=result.get("wait_duration_ms"),
            poll_count=result.get("poll_count"),
            timed_out=result.get("timed_out"),
            outcome=result.get("outcome"),
        )
