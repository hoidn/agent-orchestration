"""Loop orchestration helpers for workflow execution."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..state import ForEachState, StepResult
from .pointers import PointerResolver
from .runtime_context import RuntimeContext
from .identity import iteration_step_id

logger = logging.getLogger(__name__)


class LoopExecutor:
    """Extract for_each and repeat_until orchestration from WorkflowExecutor."""

    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def collect_persisted_iteration_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        index: int,
    ) -> Dict[str, Any]:
        """Rebuild one loop iteration from persisted presentation keys."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            return {}

        iteration_state: Dict[str, Any] = {}
        loop_results = steps_state.get(loop_name)
        if (
            isinstance(loop_results, list)
            and 0 <= index < len(loop_results)
            and isinstance(loop_results[index], dict)
        ):
            iteration_state.update(loop_results[index])

        prefix = f"{loop_name}[{index}]."
        for persisted_key, persisted_value in steps_state.items():
            if not isinstance(persisted_key, str) or not persisted_key.startswith(prefix):
                continue
            nested_name = persisted_key[len(prefix):]
            if nested_name:
                iteration_state[nested_name] = persisted_value

        return iteration_state

    def store_loop_iteration_result(
        self,
        loop_results: List[Dict[str, Any]],
        index: int,
        iteration_state: Dict[str, Any],
    ) -> None:
        """Store an iteration result at its stable list position."""
        while len(loop_results) <= index:
            loop_results.append({})
        loop_results[index] = iteration_state

    def persist_for_each_progress(
        self,
        state: Dict[str, Any],
        loop_name: str,
        items: List[Any],
        completed_indices: List[int],
        current_index: Optional[int],
        loop_results: List[Dict[str, Any]],
    ) -> None:
        """Persist loop summary and bookkeeping for durable resume."""
        state.setdefault("steps", {})
        state.setdefault("for_each", {})

        progress = {
            "items": list(items),
            "completed_indices": sorted(set(completed_indices)),
            "current_index": current_index,
        }
        state["steps"][loop_name] = loop_results
        state["for_each"][loop_name] = progress

        self.executor.state_manager.update_loop_results(loop_name, loop_results)
        self.executor.state_manager.update_for_each(
            loop_name,
            ForEachState(
                items=list(items),
                completed_indices=progress["completed_indices"],
                current_index=current_index,
            ),
        )

    def persist_repeat_until_progress(
        self,
        state: Dict[str, Any],
        loop_name: str,
        progress: Dict[str, Any],
        frame_result: Dict[str, Any],
    ) -> None:
        """Persist repeat_until bookkeeping plus the current loop-frame snapshot."""
        state.setdefault("steps", {})
        state.setdefault("repeat_until", {})
        state["steps"][loop_name] = frame_result
        state["repeat_until"][loop_name] = progress
        self.executor.state_manager.update_repeat_until_state(loop_name, progress, frame_result)

    def repeat_until_iteration_resume_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        iteration: int,
        body_steps: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], int, bool]:
        """Return persisted iteration state plus the first unfinished nested step index."""
        iteration_state = self.collect_persisted_iteration_state(state, loop_name, iteration)
        start_nested_index = 0
        for nested_index, nested_step in enumerate(body_steps):
            nested_name = nested_step.get("name", f"nested_{nested_index}")
            persisted = iteration_state.get(nested_name)
            if self.executor._resume_entry_is_terminal(persisted):
                start_nested_index = nested_index + 1
                continue
            start_nested_index = nested_index
            break
        else:
            start_nested_index = len(body_steps)

        return iteration_state, start_nested_index, start_nested_index >= len(body_steps)

    def resume_for_each_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        loop_steps: List[Dict[str, Any]],
        items: List[Any],
    ) -> tuple[List[Dict[str, Any]], List[int], int]:
        """Load persisted loop progress and determine the restart index."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        loop_results: List[Dict[str, Any]] = []
        existing_results = steps_state.get(loop_name)
        if isinstance(existing_results, list):
            loop_results = list(existing_results)

        progress = state.get("for_each", {}).get(loop_name)
        completed_indices: List[int] = []
        current_index: Optional[int] = None
        if isinstance(progress, dict):
            completed_indices = [
                index
                for index in progress.get("completed_indices", [])
                if isinstance(index, int) and 0 <= index < len(items)
            ]
            candidate_index = progress.get("current_index")
            if isinstance(candidate_index, int) and 0 <= candidate_index < len(items):
                current_index = candidate_index

        if not completed_indices and isinstance(existing_results, list):
            for i, iteration_result in enumerate(existing_results):
                if not isinstance(iteration_result, dict):
                    break
                all_steps_complete = True
                for nested_step in loop_steps:
                    nested_name = nested_step.get("name", f"step_{i}")
                    iteration_key = f"{loop_name}[{i}].{nested_name}"
                    nested_result = steps_state.get(iteration_key)
                    if not isinstance(nested_result, dict):
                        all_steps_complete = False
                        break
                    if nested_result.get("status") not in ["completed", "failed", "skipped"]:
                        all_steps_complete = False
                        break
                if not all_steps_complete:
                    current_index = i
                    break
                completed_indices.append(i)

        for index in completed_indices:
            persisted_iteration = self.collect_persisted_iteration_state(state, loop_name, index)
            if persisted_iteration:
                self.store_loop_iteration_result(loop_results, index, persisted_iteration)

        start_index = current_index if current_index is not None else 0
        while start_index in completed_indices:
            logger.info("Skipping completed iteration %s of %s", start_index, loop_name)
            start_index += 1

        return loop_results, sorted(set(completed_indices)), start_index

    def build_repeat_until_frame_result(
        self,
        step: Dict[str, Any],
        *,
        status: str,
        exit_code: int,
        artifacts: Optional[Dict[str, Any]],
        progress: Dict[str, Any],
        error: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the persisted loop-frame result for one repeat_until step."""
        metadata = step.get("repeat_until", {})
        result: Dict[str, Any] = {
            "status": status,
            "exit_code": exit_code,
            "duration_ms": 0,
            "name": step.get("name", f"step_{self.executor.current_step}"),
            "step_id": self.executor._step_id(step),
            "debug": {
                "structured_repeat_until": {
                    "body_id": metadata.get("id"),
                    "max_iterations": metadata.get("max_iterations"),
                    "current_iteration": progress.get("current_iteration"),
                    "completed_iterations": list(progress.get("completed_iterations", [])),
                    "condition_evaluated_for_iteration": progress.get("condition_evaluated_for_iteration"),
                    "last_condition_result": progress.get("last_condition_result"),
                }
            },
        }
        if isinstance(artifacts, dict):
            result["artifacts"] = artifacts
        if isinstance(error, dict):
            result["error"] = error
        return result

    def execute_repeat_until(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """Execute a post-test repeat_until loop with durable resume bookkeeping."""
        step_name = step.get("name", f"step_{self.executor.current_step}")
        block = step.get("repeat_until", {})
        body_steps = block.get("steps", []) if isinstance(block, dict) else []
        outputs = block.get("outputs", {}) if isinstance(block, dict) else {}
        condition = block.get("condition") if isinstance(block, dict) else None
        max_iterations = block.get("max_iterations") if isinstance(block, dict) else None

        if not isinstance(body_steps, list) or not isinstance(outputs, dict) or type(max_iterations) is not int:
            state["steps"][step_name] = self.executor._attach_outcome(
                step,
                self.build_repeat_until_frame_result(
                    step,
                    status="failed",
                    exit_code=2,
                    artifacts=None,
                    progress={
                        "current_iteration": 0,
                        "completed_iterations": [],
                        "condition_evaluated_for_iteration": None,
                        "last_condition_result": None,
                    },
                    error={
                        "type": "contract_violation",
                        "message": "repeat_until configuration invalid at execution time",
                    },
                ),
                phase_hint="pre_execution",
                class_hint="contract_violation",
                retryable_hint=False,
            )
            self.executor.state_manager.update_repeat_until_state(
                step_name,
                {
                    "current_iteration": 0,
                    "completed_iterations": [],
                    "condition_evaluated_for_iteration": None,
                    "last_condition_result": None,
                },
                state["steps"][step_name],
            )
            return state

        repeat_until_state = state.setdefault("repeat_until", {})
        if not isinstance(repeat_until_state, dict):
            repeat_until_state = {}
            state["repeat_until"] = repeat_until_state

        persisted_progress = repeat_until_state.get(step_name)
        if not isinstance(persisted_progress, dict):
            persisted_progress = {}

        completed_iterations = sorted(
            {
                index
                for index in persisted_progress.get("completed_iterations", [])
                if isinstance(index, int) and index >= 0
            }
        )
        current_iteration = persisted_progress.get("current_iteration")
        if not isinstance(current_iteration, int) or current_iteration < 0:
            current_iteration = 0
        condition_evaluated_for_iteration = persisted_progress.get("condition_evaluated_for_iteration")
        if not isinstance(condition_evaluated_for_iteration, int):
            condition_evaluated_for_iteration = None
        last_condition_result = persisted_progress.get("last_condition_result")
        if not isinstance(last_condition_result, bool):
            last_condition_result = None

        frame_artifacts: Dict[str, Any] = {}
        existing_frame = state.get("steps", {}).get(step_name)
        if isinstance(existing_frame, dict) and isinstance(existing_frame.get("artifacts"), dict):
            frame_artifacts = dict(existing_frame.get("artifacts", {}))

        loop_step_id = self.executor._step_id(step)
        parent_scope_steps = self.build_loop_parent_scope_steps(step, state)

        if resume and current_iteration not in completed_iterations:
            _, _, body_complete = self.repeat_until_iteration_resume_state(
                state,
                step_name,
                current_iteration,
                body_steps,
            )
            if condition_evaluated_for_iteration == current_iteration:
                if last_condition_result is True:
                    completed_iterations = sorted(set(completed_iterations + [current_iteration]))
                    progress = {
                        "current_iteration": None,
                        "completed_iterations": completed_iterations,
                        "condition_evaluated_for_iteration": current_iteration,
                        "last_condition_result": True,
                    }
                    final_result = self.executor._attach_outcome(
                        step,
                        self.build_repeat_until_frame_result(
                            step,
                            status="completed",
                            exit_code=0,
                            artifacts=frame_artifacts,
                            progress=progress,
                        ),
                    )
                    self.persist_repeat_until_progress(state, step_name, progress, final_result)
                    return state
                if body_complete:
                    completed_iterations = sorted(set(completed_iterations + [current_iteration]))
                    current_iteration += 1
                    condition_evaluated_for_iteration = None
                    last_condition_result = None

        while current_iteration < max_iterations:
            progress = {
                "current_iteration": current_iteration,
                "completed_iterations": completed_iterations,
                "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                "last_condition_result": last_condition_result,
            }
            running_frame = self.build_repeat_until_frame_result(
                step,
                status="running",
                exit_code=0,
                artifacts=frame_artifacts,
                progress=progress,
            )
            self.persist_repeat_until_progress(state, step_name, progress, running_frame)

            iteration_state, start_nested_index, body_complete = self.repeat_until_iteration_resume_state(
                state,
                step_name,
                current_iteration,
                body_steps,
            )
            loop_context = {
                "loop": {
                    "index": current_iteration,
                    "total": max_iterations,
                }
            }

            if not body_complete:
                for nested_index in range(start_nested_index, len(body_steps)):
                    nested_step = body_steps[nested_index]
                    nested_name = nested_step.get("name", f"nested_{nested_index}")
                    nested_runtime_step_id = iteration_step_id(
                        loop_step_id,
                        current_iteration,
                        nested_step,
                        nested_index,
                    )

                    loop_scope = self.build_loop_scope(state, iteration_state, parent_scope_steps)
                    result = None
                    guard = nested_step.get("structured_if_guard")
                    if isinstance(guard, dict) and isinstance(guard.get("condition"), dict):
                        result = self.evaluate_loop_body_condition(
                            nested_step,
                            guard["condition"],
                            state,
                            loop_context=loop_context,
                            scope=loop_scope,
                            runtime_step_id=nested_runtime_step_id,
                            invert=bool(guard.get("invert")),
                        )
                    if result is None and isinstance(nested_step.get("when"), dict):
                        result = self.evaluate_loop_body_condition(
                            nested_step,
                            nested_step["when"],
                            state,
                            loop_context=loop_context,
                            scope=loop_scope,
                            runtime_step_id=nested_runtime_step_id,
                        )
                    if result is not None:
                        iteration_state[nested_name] = result
                        self.executor.state_manager.update_loop_step(
                            step_name,
                            current_iteration,
                            nested_name,
                            StepResult(
                                status=result.get("status", "completed" if result.get("exit_code", 0) == 0 else "failed"),
                                name=result.get("name", nested_name),
                                step_id=result.get("step_id"),
                                exit_code=result.get("exit_code", 0),
                                duration_ms=result.get("duration_ms", 0),
                                error=result.get("error"),
                                truncated=result.get("truncated", False),
                                artifacts=result.get("artifacts"),
                                skipped=result.get("skipped", False),
                                outcome=result.get("outcome"),
                            ),
                        )
                        if result.get("skipped", False):
                            continue
                        failure_progress = {
                            "current_iteration": current_iteration,
                            "completed_iterations": completed_iterations,
                            "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                            "last_condition_result": last_condition_result,
                        }
                        failure = self.executor._attach_outcome(
                            step,
                            self.build_repeat_until_frame_result(
                                step,
                                status="failed",
                                exit_code=2,
                                artifacts=frame_artifacts,
                                progress=failure_progress,
                                error={
                                    "type": "repeat_until_body_step_failed",
                                    "message": "repeat_until body step failed",
                                    "context": {
                                        "iteration": current_iteration,
                                        "step": nested_name,
                                        "error": result.get("error"),
                                    },
                                },
                            ),
                            phase_hint="pre_execution",
                            class_hint="pre_execution_failed",
                            retryable_hint=False,
                        )
                        self.persist_repeat_until_progress(state, step_name, failure_progress, failure)
                        return state

                    nested_context = self.create_loop_context(nested_step, loop_context, iteration_state)

                    if self.executor.debug:
                        backup_name = f"{step_name}[{current_iteration}].{nested_name}"
                        self.executor.state_manager.backup_state(backup_name)

                    consume_error = self.executor._enforce_consumes_contract(
                        nested_step,
                        nested_name,
                        state,
                        runtime_step_id=nested_runtime_step_id,
                    )
                    if consume_error is not None:
                        result = consume_error
                    else:
                        result = self.executor._execute_nested_loop_step(
                            nested_step,
                            nested_context,
                            state,
                            iteration_state,
                            parent_scope_steps,
                            runtime_step_id=nested_runtime_step_id,
                            loop_name=step_name,
                            iteration_index=current_iteration,
                        )

                    if consume_error is not None:
                        result.setdefault("name", nested_name)
                        result.setdefault("step_id", nested_runtime_step_id)
                        result = self.executor._attach_outcome(nested_step, result)
                        iteration_state[nested_name] = result
                        self.executor.state_manager.update_loop_step(
                            step_name,
                            current_iteration,
                            nested_name,
                            StepResult(
                                status=result.get("status", "completed" if result.get("exit_code", 0) == 0 else "failed"),
                                name=result.get("name", nested_name),
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
                            ),
                        )

                    if result.get("exit_code", 0) != 0 and not result.get("skipped", False):
                        nested_outcome = result.get("outcome") if isinstance(result.get("outcome"), dict) else {}
                        failure_progress = {
                            "current_iteration": current_iteration,
                            "completed_iterations": completed_iterations,
                            "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                            "last_condition_result": last_condition_result,
                        }
                        failure = self.executor._attach_outcome(
                            step,
                            self.build_repeat_until_frame_result(
                                step,
                                status="failed",
                                exit_code=result.get("exit_code", 1),
                                artifacts=frame_artifacts,
                                progress=failure_progress,
                                error={
                                    "type": "repeat_until_body_step_failed",
                                    "message": "repeat_until body step failed",
                                    "context": {
                                        "iteration": current_iteration,
                                        "step": nested_name,
                                        "error": result.get("error"),
                                    },
                                },
                            ),
                            phase_hint=nested_outcome.get("phase"),
                            class_hint=nested_outcome.get("class"),
                            retryable_hint=nested_outcome.get("retryable"),
                        )
                        self.persist_repeat_until_progress(state, step_name, failure_progress, failure)
                        return state

            artifacts = self.executor._resolve_structured_output_artifacts(
                outputs,
                state,
                failure_message="repeat_until output resolution failed",
                selection_key="iteration",
                selection_value=str(current_iteration),
                scope={
                    "self_steps": iteration_state,
                    "parent_steps": parent_scope_steps,
                    "root_steps": state.get("steps", {}),
                },
            )
            if not isinstance(artifacts, dict):
                failure_progress = {
                    "current_iteration": current_iteration,
                    "completed_iterations": completed_iterations,
                    "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                    "last_condition_result": last_condition_result,
                }
                failure = self.executor._attach_outcome(
                    step,
                    self.build_repeat_until_frame_result(
                        step,
                        status="failed",
                        exit_code=2,
                        artifacts=frame_artifacts,
                        progress=failure_progress,
                        error=artifacts.get("error") if isinstance(artifacts, dict) else None,
                    ),
                    phase_hint="post_execution",
                    class_hint="contract_violation",
                    retryable_hint=False,
                )
                self.persist_repeat_until_progress(state, step_name, failure_progress, failure)
                return state

            frame_artifacts = artifacts
            progress = {
                "current_iteration": current_iteration,
                "completed_iterations": completed_iterations,
                "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                "last_condition_result": last_condition_result,
            }
            self.persist_repeat_until_progress(
                state,
                step_name,
                progress,
                self.build_repeat_until_frame_result(
                    step,
                    status="running",
                    exit_code=0,
                    artifacts=frame_artifacts,
                    progress=progress,
                ),
            )

            if condition_evaluated_for_iteration != current_iteration:
                runtime_context = self.executor._runtime_context({}, state)
                variables = runtime_context.build_variables(self.executor.variable_substitutor, state)
                try:
                    should_stop = self.executor.condition_evaluator.evaluate(condition, variables, state)
                except Exception as exc:
                    failure_progress = {
                        "current_iteration": current_iteration,
                        "completed_iterations": completed_iterations,
                        "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                        "last_condition_result": last_condition_result,
                    }
                    failure = self.executor._attach_outcome(
                        step,
                        self.build_repeat_until_frame_result(
                            step,
                            status="failed",
                            exit_code=2,
                            artifacts=frame_artifacts,
                            progress=failure_progress,
                            error={
                                "type": "predicate_evaluation_failed",
                                "message": f"repeat_until condition evaluation failed: {exc}",
                                "context": {"condition": condition, "iteration": current_iteration},
                            },
                        ),
                        phase_hint="post_execution",
                        class_hint="contract_violation",
                        retryable_hint=False,
                    )
                    self.persist_repeat_until_progress(state, step_name, failure_progress, failure)
                    return state
                condition_evaluated_for_iteration = current_iteration
                last_condition_result = should_stop
                progress = {
                    "current_iteration": current_iteration,
                    "completed_iterations": completed_iterations,
                    "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                    "last_condition_result": last_condition_result,
                }
                self.persist_repeat_until_progress(
                    state,
                    step_name,
                    progress,
                    self.build_repeat_until_frame_result(
                        step,
                        status="running",
                        exit_code=0,
                        artifacts=frame_artifacts,
                        progress=progress,
                    ),
                )
            else:
                should_stop = bool(last_condition_result)

            completed_iterations = sorted(set(completed_iterations + [current_iteration]))
            if should_stop:
                progress = {
                    "current_iteration": None,
                    "completed_iterations": completed_iterations,
                    "condition_evaluated_for_iteration": current_iteration,
                    "last_condition_result": True,
                }
                completed = self.executor._attach_outcome(
                    step,
                    self.build_repeat_until_frame_result(
                        step,
                        status="completed",
                        exit_code=0,
                        artifacts=frame_artifacts,
                        progress=progress,
                    ),
                )
                self.persist_repeat_until_progress(state, step_name, progress, completed)
                return state

            if current_iteration + 1 >= max_iterations:
                progress = {
                    "current_iteration": None,
                    "completed_iterations": completed_iterations,
                    "condition_evaluated_for_iteration": current_iteration,
                    "last_condition_result": False,
                }
                exhausted = self.executor._attach_outcome(
                    step,
                    self.build_repeat_until_frame_result(
                        step,
                        status="failed",
                        exit_code=3,
                        artifacts=frame_artifacts,
                        progress=progress,
                        error={
                            "type": "repeat_until_iterations_exhausted",
                            "message": "repeat_until exhausted max_iterations before condition became true",
                            "context": {
                                "max_iterations": max_iterations,
                                "last_iteration": current_iteration,
                            },
                        },
                    ),
                    phase_hint="post_execution",
                    class_hint="assert_failed",
                    retryable_hint=False,
                )
                self.persist_repeat_until_progress(state, step_name, progress, exhausted)
                return state

            current_iteration += 1
            condition_evaluated_for_iteration = None
            last_condition_result = None

        return state

    def execute_for_each(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """Execute a for_each loop step."""
        step_name = step.get("name", f"step_{self.executor.current_step}")
        for_each = step["for_each"]
        persisted_progress = (
            state.get("for_each", {}).get(step_name)
            if isinstance(state.get("for_each"), dict)
            else None
        )

        if resume and isinstance(persisted_progress, dict) and isinstance(persisted_progress.get("items"), list):
            items = list(persisted_progress.get("items", []))
        elif "items_from" in for_each:
            pointer_resolver = PointerResolver(state)
            try:
                items = pointer_resolver.resolve(for_each["items_from"])
            except ValueError as exc:
                return self.executor._record_step_error(
                    state,
                    step_name,
                    exit_code=2,
                    error={
                        "message": f"Failed to resolve items_from pointer: {exc}",
                        "context": {
                            "pointer": for_each["items_from"],
                            "error": str(exc),
                        },
                    },
                )
            if not isinstance(items, list):
                return self.executor._record_step_error(
                    state,
                    step_name,
                    exit_code=2,
                    error={
                        "message": f"items_from must resolve to an array, got {type(items).__name__}",
                        "context": {
                            "pointer": for_each["items_from"],
                            "resolved_type": type(items).__name__,
                        },
                    },
                )
        else:
            items = list(for_each.get("items", []))

        item_var = for_each.get("as", "item")
        loop_steps = for_each.get("steps", [])

        if "steps" not in state:
            state["steps"] = {}
        state.setdefault("for_each", {})

        loop_results: List[Dict[str, Any]] = []
        completed_indices: List[int] = []

        start_index = 0
        if resume:
            loop_results, completed_indices, start_index = self.resume_for_each_state(
                state,
                step_name,
                loop_steps,
                items,
            )

        self.persist_for_each_progress(
            state,
            step_name,
            items,
            completed_indices,
            start_index if start_index < len(items) else None,
            loop_results,
        )

        loop_step_id = self.executor._step_id(step)
        parent_scope_steps = self.build_loop_parent_scope_steps(step, state)
        for index in range(start_index, len(items)):
            item = items[index]
            self.persist_for_each_progress(
                state,
                step_name,
                items,
                completed_indices,
                index,
                loop_results,
            )

            loop_context = {
                "item": item,
                item_var: item,
                "loop": {
                    "index": index,
                    "total": len(items),
                },
            }

            iteration_state: Dict[str, Any] = {}
            for nested_index, nested_step in enumerate(loop_steps):
                nested_name = nested_step.get("name", f"nested_{index}")
                nested_runtime_step_id = iteration_step_id(loop_step_id, index, nested_step, nested_index)

                if "when" in nested_step:
                    nested_runtime_context = self.executor._runtime_context(loop_context, state, parent_steps=parent_scope_steps)
                    variables = nested_runtime_context.build_variables(self.executor.variable_substitutor, state)

                    try:
                        should_execute = self.executor.condition_evaluator.evaluate(
                            nested_step["when"],
                            variables,
                            state,
                            scope=nested_runtime_context.scope() | {"self_steps": iteration_state},
                        )
                    except Exception as exc:
                        result = {
                            "status": "failed",
                            "exit_code": 2,
                            "error": {
                                "type": "predicate_evaluation_failed",
                                "message": f"Condition evaluation failed: {exc}",
                                "context": {"condition": nested_step["when"]},
                            },
                        }
                        result.setdefault("name", nested_name)
                        result.setdefault("step_id", nested_runtime_step_id)
                        result = self.executor._attach_outcome(nested_step, result)
                        iteration_state[nested_name] = result
                        self.executor.state_manager.update_loop_step(
                            step_name,
                            index,
                            nested_name,
                            StepResult(
                                status=result.get("status", "failed"),
                                name=result.get("name", nested_name),
                                step_id=result.get("step_id"),
                                exit_code=result.get("exit_code", 2),
                                duration_ms=result.get("duration_ms", 0),
                                error=result.get("error"),
                                truncated=result.get("truncated", False),
                                artifacts=result.get("artifacts"),
                                skipped=result.get("skipped", False),
                                outcome=result.get("outcome"),
                            ),
                        )
                        continue

                    if not should_execute:
                        result = {
                            "status": "skipped",
                            "exit_code": 0,
                            "skipped": True,
                        }
                        result.setdefault("name", nested_name)
                        result.setdefault("step_id", nested_runtime_step_id)
                        result = self.executor._attach_outcome(nested_step, result)
                        iteration_state[nested_name] = result
                        self.executor.state_manager.update_loop_step(
                            step_name,
                            index,
                            nested_name,
                            StepResult(
                                status=result.get("status", "skipped"),
                                name=result.get("name", nested_name),
                                step_id=result.get("step_id"),
                                exit_code=result.get("exit_code", 0),
                                duration_ms=result.get("duration_ms", 0),
                                truncated=result.get("truncated", False),
                                artifacts=result.get("artifacts"),
                                skipped=result.get("skipped", True),
                                outcome=result.get("outcome"),
                            ),
                        )
                        continue

                nested_context = self.create_loop_context(nested_step, loop_context, iteration_state)

                if self.executor.debug:
                    backup_name = f"{step_name}[{index}].{nested_name}"
                    self.executor.state_manager.backup_state(backup_name)

                consume_error = self.executor._enforce_consumes_contract(
                    nested_step,
                    nested_name,
                    state,
                    runtime_step_id=nested_runtime_step_id,
                )
                if consume_error is not None:
                    result = consume_error
                else:
                    result = self.executor._execute_nested_loop_step(
                        nested_step,
                        nested_context,
                        state,
                        iteration_state,
                        parent_scope_steps,
                        runtime_step_id=nested_runtime_step_id,
                        loop_name=step_name,
                        iteration_index=index,
                    )

                if consume_error is not None:
                    result.setdefault("name", nested_name)
                    result.setdefault("step_id", nested_runtime_step_id)
                    result = self.executor._attach_outcome(nested_step, result)
                    iteration_state[nested_name] = result

                    self.executor.state_manager.update_loop_step(
                        step_name,
                        index,
                        nested_name,
                        StepResult(
                            status=result.get("status", "completed" if result.get("exit_code", 0) == 0 else "failed"),
                            name=result.get("name", nested_name),
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
                        ),
                    )

            self.store_loop_iteration_result(loop_results, index, iteration_state)
            completed_indices.append(index)
            next_index = index + 1 if index + 1 < len(items) else None
            self.persist_for_each_progress(
                state,
                step_name,
                items,
                completed_indices,
                next_index,
                loop_results,
            )

        state["steps"][step_name] = loop_results

        for i, iteration in enumerate(loop_results):
            for nested_name, result in iteration.items():
                indexed_key = f"{step_name}[{i}].{nested_name}"
                state["steps"][indexed_key] = result

        self.persist_for_each_progress(
            state,
            step_name,
            items,
            completed_indices,
            None,
            loop_results,
        )

        return state

    def build_loop_parent_scope_steps(
        self,
        loop_step: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the lexical parent scope for structured refs inside one loop body."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            return {}

        loop_step_id = self.executor._step_id(loop_step)
        if "." in loop_step_id:
            parent_step_id = loop_step_id.rsplit(".", 1)[0]
        else:
            parent_step_id = "root"

        loop_name = loop_step.get("name")
        name_prefix = None
        if isinstance(loop_name, str) and "." in loop_name:
            name_prefix = loop_name.rsplit(".", 1)[0]

        parent_scope_steps: Dict[str, Any] = {}
        for candidate in self.executor.steps:
            if not isinstance(candidate, dict):
                continue
            candidate_name = candidate.get("name")
            candidate_step_id = candidate.get("step_id")
            if not isinstance(candidate_name, str) or not isinstance(candidate_step_id, str):
                continue
            if "." in candidate_step_id:
                candidate_parent_id = candidate_step_id.rsplit(".", 1)[0]
            else:
                candidate_parent_id = "root"
            if candidate_parent_id != parent_step_id:
                continue

            candidate_result = steps_state.get(candidate_name)
            if not isinstance(candidate_result, dict):
                continue

            if name_prefix and candidate_name.startswith(f"{name_prefix}."):
                local_name = candidate_name[len(name_prefix) + 1:]
            else:
                local_name = candidate_name
            parent_scope_steps[local_name] = candidate_result

        return parent_scope_steps

    def build_loop_scope(
        self,
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        """Build structured-ref scope maps for one nested loop step."""
        return {
            "self_steps": iteration_state,
            "parent_steps": parent_scope_steps,
            "root_steps": state.get("steps", {}),
        }

    def evaluate_loop_body_condition(
        self,
        step: Dict[str, Any],
        condition: Dict[str, Any],
        state: Dict[str, Any],
        *,
        loop_context: Dict[str, Any],
        scope: Dict[str, Dict[str, Any]],
        runtime_step_id: str,
        invert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate one loop-body guard/when condition and return failure or skip results."""
        runtime_context = RuntimeContext.from_mapping(
            loop_context,
            default_context=self.executor.workflow.get("context", {}),
            parent_steps=scope.get("parent_steps", {}),
            root_steps=scope.get("root_steps", {}),
        )
        runtime_context = RuntimeContext(
            values=runtime_context.values,
            workflow_context=runtime_context.workflow_context,
            self_steps=scope.get("self_steps", {}),
            explicit_steps=True,
            parent_steps=runtime_context.parent_steps,
            root_steps=runtime_context.root_steps,
        )
        variables = runtime_context.build_variables(self.executor.variable_substitutor, state)
        try:
            should_execute = self.executor.condition_evaluator.evaluate(
                condition,
                variables,
                state,
                scope=runtime_context.scope(),
            )
            if invert:
                should_execute = not should_execute
        except Exception as exc:
            return self.executor._attach_outcome(
                step,
                {
                    "status": "failed",
                    "exit_code": 2,
                    "name": step.get("name", f"nested_{self.executor.current_step}"),
                    "step_id": runtime_step_id,
                    "error": {
                        "type": "predicate_evaluation_failed",
                        "message": f"Condition evaluation failed: {exc}",
                        "context": {"condition": condition},
                    },
                },
                phase_hint="pre_execution",
                class_hint="pre_execution_failed",
                retryable_hint=False,
            )

        if should_execute:
            return None

        return self.executor._attach_outcome(
            step,
            {
                "status": "skipped",
                "exit_code": 0,
                "skipped": True,
                "name": step.get("name", f"nested_{self.executor.current_step}"),
                "step_id": runtime_step_id,
            },
        )

    def create_loop_context(
        self,
        step: Dict[str, Any],
        loop_context: Dict[str, Any],
        iteration_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create variable substitution context for a loop iteration."""
        del step
        run_state = self.executor.state_manager.load()
        run_metadata = {
            "id": run_state.run_id,
            "root": run_state.run_root,
            "timestamp_utc": run_state.started_at,
        }

        workflow_context = run_state.context if isinstance(run_state.context, dict) else self.executor.variables

        return {
            "run": run_metadata,
            "context": workflow_context,
            "steps": iteration_state,
            **loop_context,
        }
