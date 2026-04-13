"""Loop orchestration helpers for workflow execution."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from ..state import ForEachState, StepResult
from .executable_ir import ExecutableNodeKind
from .pointers import PointerResolver
from .runtime_context import RuntimeContext
from .identity import iteration_step_id
from .state_projection import IterationStepKeyProjection

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

    def persist_loop_iteration_step_result(
        self,
        state: Dict[str, Any],
        loop_name: str,
        index: int,
        nested_name: str,
        iteration_state: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Persist one loop-iteration step result in memory and state.json."""
        iteration_state[nested_name] = result
        state.setdefault("steps", {})[f"{loop_name}[{index}].{nested_name}"] = result
        self.executor.state_manager.update_loop_step(
            loop_name,
            index,
            nested_name,
            self.executor._to_step_result(result, nested_name),
        )

    def _typed_loop_body_context(
        self,
        loop_step: Dict[str, Any],
        *,
        loop_kind: str,
    ) -> Optional[tuple[str, tuple[str, ...], IterationStepKeyProjection]]:
        """Return typed loop-body metadata when this loop is backed by executable IR."""
        projection = getattr(self.executor, "projection", None)
        loop_node = self.executor._executable_node_for_step(loop_step)
        if projection is None or loop_node is None:
            return None

        expected_kind = (
            ExecutableNodeKind.REPEAT_UNTIL_FRAME
            if loop_kind == "repeat_until"
            else ExecutableNodeKind.FOR_EACH
        )
        if getattr(loop_node, "kind", None) != expected_kind:
            return None

        if loop_kind == "repeat_until":
            loop_projection = projection.repeat_until_nodes.get(loop_node.node_id)
        else:
            loop_projection = projection.for_each_nodes.get(loop_node.node_id)
        if loop_projection is None:
            return None

        body_node_ids = tuple(
            node_id
            for node_id in getattr(loop_node, "body_node_ids", ())
            if isinstance(node_id, str) and node_id
        )
        return loop_node.node_id, body_node_ids, loop_projection

    def _typed_loop_next_node_id(
        self,
        current_node_id: str,
        result: Dict[str, Any],
        body_node_ids: tuple[str, ...],
    ) -> Optional[str]:
        """Return the next typed loop-body node id after one nested result settles."""
        target_node_id = None
        implicit_transfer = self.executor._implicit_typed_transfer_for_result(
            current_node_id,
            skipped=bool(result.get("skipped", False)),
        )
        if implicit_transfer is not None:
            target_node_id = implicit_transfer.target_node_id
        elif self.executor.executable_ir is not None:
            node = self.executor.executable_ir.nodes.get(current_node_id)
            if node is not None:
                target_node_id = node.fallthrough_node_id

        if isinstance(target_node_id, str) and target_node_id in body_node_ids:
            return target_node_id
        return None

    def _persist_typed_loop_skipped_descendants(
        self,
        *,
        state: Dict[str, Any],
        loop_name: str,
        iteration_index: int,
        iteration_state: Dict[str, Any],
        current_node_id: str,
        body_node_ids: tuple[str, ...],
        loop_projection: IterationStepKeyProjection,
    ) -> None:
        """Persist skipped descendants for one skipped typed branch or case marker."""
        descendant_prefix = f"{current_node_id}."
        for node_id in body_node_ids:
            if not node_id.startswith(descendant_prefix):
                continue
            nested_name = loop_projection.nested_presentation_keys.get(node_id)
            if not isinstance(nested_name, str) or not nested_name or nested_name in iteration_state:
                continue
            nested_step = self.executor._runtime_step_for_node_id(
                node_id,
                presentation_name=nested_name,
                step_id=loop_projection.runtime_step_id(iteration_index, node_id),
            )
            skipped_result = self.executor._attach_outcome(
                nested_step,
                {
                    "status": "skipped",
                    "exit_code": 0,
                    "skipped": True,
                    "name": nested_name,
                    "step_id": loop_projection.runtime_step_id(iteration_index, node_id),
                },
            )
            self.persist_loop_iteration_step_result(
                state,
                loop_name,
                iteration_index,
                nested_name,
                iteration_state,
                skipped_result,
            )

    def _execute_typed_loop_body(
        self,
        *,
        state: Dict[str, Any],
        loop_step: Dict[str, Any],
        loop_name: str,
        iteration_index: int,
        iteration_state: Dict[str, Any],
        start_node_id: Optional[str],
        body_node_ids: tuple[str, ...],
        loop_projection: IterationStepKeyProjection,
        loop_context: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        parent_scope_node_results: Dict[str, Any],
        stop_on_failure: bool,
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """Execute one typed loop body by IR node ids until the frame boundary or failure."""
        current_node_id = start_node_id
        while isinstance(current_node_id, str) and current_node_id in body_node_ids:
            nested_runtime_step_id = loop_projection.runtime_step_id(iteration_index, current_node_id)
            projected_nested_name = loop_projection.nested_presentation_keys.get(current_node_id)
            nested_step = self.executor._runtime_step_for_node_id(
                current_node_id,
                presentation_name=projected_nested_name if isinstance(projected_nested_name, str) else None,
                step_id=nested_runtime_step_id,
            )
            nested_name = (
                projected_nested_name
                if isinstance(projected_nested_name, str) and projected_nested_name
                else nested_step.get("name", current_node_id)
            )
            loop_scope = self.build_loop_scope(
                state,
                iteration_state,
                parent_scope_steps,
                loop_step=loop_step,
                parent_scope_node_results=parent_scope_node_results,
            )

            result = None
            guard_condition, invert = self.executor._structured_guard_condition(nested_step)
            if guard_condition is not None:
                result = self.evaluate_loop_body_condition(
                    nested_step,
                    guard_condition,
                    state,
                    loop_context=loop_context,
                    scope=loop_scope,
                    runtime_step_id=nested_runtime_step_id,
                    invert=invert,
                )
            when_condition = self.executor._when_condition(nested_step)
            if result is None and when_condition is not None:
                result = self.evaluate_loop_body_condition(
                    nested_step,
                    when_condition,
                    state,
                    loop_context=loop_context,
                    scope=loop_scope,
                    runtime_step_id=nested_runtime_step_id,
                )

            if result is not None:
                self.persist_loop_iteration_step_result(
                    state,
                    loop_name,
                    iteration_index,
                    nested_name,
                    iteration_state,
                    result,
                )
                if result.get("skipped", False):
                    self._persist_typed_loop_skipped_descendants(
                        state=state,
                        loop_name=loop_name,
                        iteration_index=iteration_index,
                        iteration_state=iteration_state,
                        current_node_id=current_node_id,
                        body_node_ids=body_node_ids,
                        loop_projection=loop_projection,
                    )
                    current_node_id = self._typed_loop_next_node_id(
                        current_node_id,
                        result,
                        body_node_ids,
                    )
                    continue
                if stop_on_failure:
                    return nested_name, result
                current_node_id = self._typed_loop_next_node_id(
                    current_node_id,
                    result,
                    body_node_ids,
                )
                continue

            nested_context = self.create_loop_context(nested_step, loop_context, iteration_state)
            if self.executor.debug:
                self.executor.state_manager.backup_state(
                    f"{loop_name}[{iteration_index}].{nested_name}"
                )

            consume_error = self.executor._enforce_consumes_contract(
                nested_step,
                nested_name,
                state,
                runtime_step_id=nested_runtime_step_id,
            )
            if consume_error is not None:
                consume_error.setdefault("name", nested_name)
                consume_error.setdefault("step_id", nested_runtime_step_id)
                result = self.executor._attach_outcome(nested_step, consume_error)
                self.persist_loop_iteration_step_result(
                    state,
                    loop_name,
                    iteration_index,
                    nested_name,
                    iteration_state,
                    result,
                )
            else:
                result = self.executor._execute_nested_loop_step(
                    nested_step,
                    nested_context,
                    state,
                    iteration_state,
                    parent_scope_steps,
                    loop_step=loop_step,
                    parent_scope_node_results=parent_scope_node_results,
                    runtime_step_id=nested_runtime_step_id,
                    loop_name=loop_name,
                    iteration_index=iteration_index,
                )

            if stop_on_failure and result.get("exit_code", 0) != 0 and not result.get("skipped", False):
                return nested_name, result

            if result.get("skipped", False):
                self._persist_typed_loop_skipped_descendants(
                    state=state,
                    loop_name=loop_name,
                    iteration_index=iteration_index,
                    iteration_state=iteration_state,
                    current_node_id=current_node_id,
                    body_node_ids=body_node_ids,
                    loop_projection=loop_projection,
                )
            current_node_id = self._typed_loop_next_node_id(
                current_node_id,
                result,
                body_node_ids,
            )

        return None

    def _typed_iteration_resume_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        iteration: int,
        body_node_ids: tuple[str, ...],
        loop_projection: IterationStepKeyProjection,
    ) -> tuple[Dict[str, Any], Optional[str], bool]:
        """Return persisted typed-loop iteration state plus the first unfinished node id."""
        iteration_state = self.collect_persisted_iteration_state(state, loop_name, iteration)
        for node_id in body_node_ids:
            nested_name = loop_projection.nested_presentation_keys.get(node_id)
            if not isinstance(nested_name, str) or not nested_name:
                continue
            persisted = iteration_state.get(nested_name)
            if self.executor._resume_entry_is_terminal(persisted):
                continue
            return iteration_state, node_id, False
        return iteration_state, None, True

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

    def typed_resume_for_each_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        body_node_ids: tuple[str, ...],
        loop_projection: IterationStepKeyProjection,
        items: List[Any],
    ) -> tuple[List[Dict[str, Any]], List[int], int]:
        """Load persisted loop progress for a typed for_each body without step-list scans."""
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
            nested_names = [
                loop_projection.nested_presentation_keys.get(node_id)
                for node_id in body_node_ids
            ]
            nested_names = [
                nested_name
                for nested_name in nested_names
                if isinstance(nested_name, str) and nested_name
            ]
            for i, iteration_result in enumerate(existing_results):
                if not isinstance(iteration_result, dict):
                    break
                all_steps_complete = True
                for nested_name in nested_names:
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
        outputs = self.executor._repeat_until_output_contracts(step)
        condition = self.executor._repeat_until_condition(step)
        max_iterations = block.get("max_iterations") if isinstance(block, dict) else None

        if not isinstance(body_steps, list) or not isinstance(outputs, Mapping) or type(max_iterations) is not int:
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
        parent_scope_node_results = self.build_loop_parent_scope_node_results(step, state)
        typed_body_context = self._typed_loop_body_context(step, loop_kind="repeat_until")

        if resume and current_iteration not in completed_iterations:
            if typed_body_context is not None:
                _loop_node_id, body_node_ids, loop_projection = typed_body_context
                _, _start_node_id, body_complete = self._typed_iteration_resume_state(
                    state,
                    step_name,
                    current_iteration,
                    body_node_ids,
                    loop_projection,
                )
            else:
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

            if typed_body_context is not None:
                _loop_node_id, body_node_ids, loop_projection = typed_body_context
                iteration_state, start_node_id, body_complete = self._typed_iteration_resume_state(
                    state,
                    step_name,
                    current_iteration,
                    body_node_ids,
                    loop_projection,
                )
            else:
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
                failure_name = None
                failure_result = None
                if typed_body_context is not None:
                    _loop_node_id, body_node_ids, loop_projection = typed_body_context
                    typed_failure = self._execute_typed_loop_body(
                        state=state,
                        loop_step=step,
                        loop_name=step_name,
                        iteration_index=current_iteration,
                        iteration_state=iteration_state,
                        start_node_id=start_node_id,
                        body_node_ids=body_node_ids,
                        loop_projection=loop_projection,
                        loop_context=loop_context,
                        parent_scope_steps=parent_scope_steps,
                        parent_scope_node_results=parent_scope_node_results,
                        stop_on_failure=True,
                    )
                    if typed_failure is not None:
                        failure_name, failure_result = typed_failure
                else:
                    for nested_index in range(start_nested_index, len(body_steps)):
                        nested_step = body_steps[nested_index]
                        nested_name = nested_step.get("name", f"nested_{nested_index}")
                        nested_runtime_step_id = iteration_step_id(
                            loop_step_id,
                            current_iteration,
                            nested_step,
                            nested_index,
                        )

                        loop_scope = self.build_loop_scope(
                            state,
                            iteration_state,
                            parent_scope_steps,
                            loop_step=step,
                            parent_scope_node_results=parent_scope_node_results,
                        )
                        result = None
                        guard_condition, invert = self.executor._structured_guard_condition(nested_step)
                        if guard_condition is not None:
                            result = self.evaluate_loop_body_condition(
                                nested_step,
                                guard_condition,
                                state,
                                loop_context=loop_context,
                                scope=loop_scope,
                                runtime_step_id=nested_runtime_step_id,
                                invert=invert,
                            )
                        when_condition = self.executor._when_condition(nested_step)
                        if result is None and when_condition is not None:
                            result = self.evaluate_loop_body_condition(
                                nested_step,
                                when_condition,
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
                            failure_name, failure_result = nested_name, result
                            break

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
                                loop_step=step,
                                parent_scope_node_results=parent_scope_node_results,
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
                            failure_name, failure_result = nested_name, result
                            break

                if failure_result is not None:
                    failure_progress = {
                        "current_iteration": current_iteration,
                        "completed_iterations": completed_iterations,
                        "condition_evaluated_for_iteration": condition_evaluated_for_iteration,
                        "last_condition_result": last_condition_result,
                    }
                    nested_outcome = (
                        failure_result.get("outcome")
                        if isinstance(failure_result.get("outcome"), dict)
                        else {}
                    )
                    phase_hint = (
                        nested_outcome.get("phase")
                        if nested_outcome
                        else "pre_execution"
                    )
                    class_hint = (
                        nested_outcome.get("class")
                        if nested_outcome
                        else "pre_execution_failed"
                    )
                    retryable_hint = (
                        nested_outcome.get("retryable")
                        if nested_outcome
                        else False
                    )
                    failure = self.executor._attach_outcome(
                        step,
                        self.build_repeat_until_frame_result(
                            step,
                            status="failed",
                            exit_code=failure_result.get("exit_code", 1),
                            artifacts=frame_artifacts,
                            progress=failure_progress,
                            error={
                                "type": "repeat_until_body_step_failed",
                                "message": "repeat_until body step failed",
                                "context": {
                                    "iteration": current_iteration,
                                    "step": failure_name,
                                    "error": failure_result.get("error"),
                                },
                            },
                        ),
                        phase_hint=phase_hint,
                        class_hint=class_hint,
                        retryable_hint=retryable_hint,
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
                    should_stop = self.executor._evaluate_condition_expression(
                        condition,
                        variables,
                        state,
                    )
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
                                "context": {
                                    "condition": self.executor._json_safe_runtime_value(condition),
                                    "iteration": current_iteration,
                                },
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
            typed_body_context = self._typed_loop_body_context(step, loop_kind="for_each")
            if typed_body_context is not None:
                _loop_node_id, body_node_ids, loop_projection = typed_body_context
                loop_results, completed_indices, start_index = self.typed_resume_for_each_state(
                    state,
                    step_name,
                    body_node_ids,
                    loop_projection,
                    items,
                )
            else:
                loop_results, completed_indices, start_index = self.resume_for_each_state(
                    state,
                    step_name,
                    loop_steps,
                    items,
                )
        else:
            typed_body_context = self._typed_loop_body_context(step, loop_kind="for_each")

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
        parent_scope_node_results = self.build_loop_parent_scope_node_results(step, state)
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

            if resume and index == start_index:
                if typed_body_context is not None:
                    _loop_node_id, body_node_ids, loop_projection = typed_body_context
                    iteration_state, start_node_id, _ = self._typed_iteration_resume_state(
                        state,
                        step_name,
                        index,
                        body_node_ids,
                        loop_projection,
                    )
                else:
                    iteration_state, start_nested_index, _ = self.repeat_until_iteration_resume_state(
                        state,
                        step_name,
                        index,
                        loop_steps,
                    )
            else:
                iteration_state = {}
                start_nested_index = 0
                start_node_id = None

            if typed_body_context is not None:
                _loop_node_id, body_node_ids, loop_projection = typed_body_context
                if start_node_id is None:
                    start_node_id = body_node_ids[0] if body_node_ids else None
                self._execute_typed_loop_body(
                    state=state,
                    loop_step=step,
                    loop_name=step_name,
                    iteration_index=index,
                    iteration_state=iteration_state,
                    start_node_id=start_node_id,
                    body_node_ids=body_node_ids,
                    loop_projection=loop_projection,
                    loop_context=loop_context,
                    parent_scope_steps=parent_scope_steps,
                    parent_scope_node_results=parent_scope_node_results,
                    stop_on_failure=False,
                )
            else:
                for nested_index in range(start_nested_index, len(loop_steps)):
                    nested_step = loop_steps[nested_index]
                    nested_name = nested_step.get("name", f"nested_{index}")
                    nested_runtime_step_id = iteration_step_id(loop_step_id, index, nested_step, nested_index)

                    loop_scope = self.build_loop_scope(
                        state,
                        iteration_state,
                        parent_scope_steps,
                        loop_step=step,
                        parent_scope_node_results=parent_scope_node_results,
                    )
                    guard_condition, invert = self.executor._structured_guard_condition(nested_step)
                    when_condition = self.executor._when_condition(nested_step)
                    if guard_condition is not None or when_condition is not None:
                        nested_runtime_context = self.executor._runtime_context(
                            loop_context,
                            state,
                            parent_steps=parent_scope_steps,
                        )
                        variables = nested_runtime_context.build_variables(self.executor.variable_substitutor, state)

                        try:
                            condition = guard_condition if guard_condition is not None else when_condition
                            should_execute = self.executor._evaluate_condition_expression(
                                condition,
                                variables,
                                state,
                                scope=loop_scope,
                            )
                            if guard_condition is not None and invert:
                                should_execute = not should_execute
                        except Exception as exc:
                            result = {
                                "status": "failed",
                                "exit_code": 2,
                                "error": {
                                    "type": "predicate_evaluation_failed",
                                    "message": f"Condition evaluation failed: {exc}",
                                    "context": {
                                        "condition": self.executor._json_safe_runtime_value(
                                            condition
                                        ),
                                    },
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
                            loop_step=step,
                            parent_scope_node_results=parent_scope_node_results,
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

        projection = getattr(self.executor, "projection", None)
        if projection is None:
            return {}

        parent_scope_steps: Dict[str, Any] = {}
        for entry in projection.entries_by_node_id.values():
            candidate_name = entry.presentation_key
            candidate_step_id = entry.step_id
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

    def build_loop_parent_scope_node_results(
        self,
        loop_step: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a deterministic node-id index for one loop body's lexical parent scope."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            return {}

        loop_step_id = self.executor._step_id(loop_step)
        if "." in loop_step_id:
            parent_step_id = loop_step_id.rsplit(".", 1)[0]
        else:
            parent_step_id = "root"

        projection = getattr(self.executor, "projection", None)
        if projection is None:
            return {}

        parent_scope_nodes: Dict[str, Any] = {}
        for entry in projection.entries_by_node_id.values():
            candidate_step_id = entry.step_id
            candidate_name = entry.presentation_key
            if not isinstance(candidate_step_id, str) or not isinstance(candidate_name, str):
                continue
            if "." in candidate_step_id:
                candidate_parent_id = candidate_step_id.rsplit(".", 1)[0]
            else:
                candidate_parent_id = "root"
            if candidate_parent_id != parent_step_id:
                continue

            candidate_result = steps_state.get(candidate_name)
            if isinstance(candidate_result, dict):
                parent_scope_nodes[candidate_step_id] = candidate_result

        return parent_scope_nodes

    def build_loop_self_node_results(
        self,
        loop_step: Dict[str, Any],
        iteration_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a deterministic node-id index for one active loop iteration."""
        projection = getattr(self.executor, "projection", None)
        if projection is None or not isinstance(iteration_state, dict):
            return {}

        loop_node_id = self.executor._step_id(loop_step)
        loop_projection = projection.repeat_until_nodes.get(loop_node_id)
        if loop_projection is None:
            loop_projection = projection.for_each_nodes.get(loop_node_id)
        if loop_projection is None:
            return {}

        return {
            node_id: iteration_state[presentation_key]
            for node_id, presentation_key in loop_projection.nested_presentation_keys.items()
            if presentation_key in iteration_state and isinstance(iteration_state[presentation_key], dict)
        }

    def build_loop_self_node_ids(self, loop_step: Dict[str, Any]) -> tuple[str, ...]:
        """Return node ids that belong to the active loop body scope."""
        projection = getattr(self.executor, "projection", None)
        if projection is None:
            return ()

        loop_node_id = self.executor._step_id(loop_step)
        loop_projection = projection.repeat_until_nodes.get(loop_node_id)
        if loop_projection is None:
            loop_projection = projection.for_each_nodes.get(loop_node_id)
        if loop_projection is None:
            return ()

        return tuple(loop_projection.nested_presentation_keys.keys())

    def build_loop_scope(
        self,
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        *,
        loop_step: Optional[Dict[str, Any]] = None,
        parent_scope_node_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Build structured-ref scope maps for one nested loop step."""
        scope: Dict[str, Dict[str, Any]] = {
            "self_steps": iteration_state,
            "parent_steps": parent_scope_steps,
            "root_steps": state.get("steps", {}),
        }
        if isinstance(parent_scope_node_results, dict) and parent_scope_node_results:
            scope["parent_node_results"] = parent_scope_node_results
        if loop_step is not None:
            self_node_ids = self.build_loop_self_node_ids(loop_step)
            if self_node_ids:
                scope["self_node_ids"] = self_node_ids
            self_node_results = self.build_loop_self_node_results(loop_step, iteration_state)
            if self_node_results:
                scope["self_node_results"] = self_node_results
        return scope

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
            default_context=self.executor.workflow_context_defaults,
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
            should_execute = self.executor._evaluate_condition_expression(
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
                        "context": {
                            "condition": self.executor._json_safe_runtime_value(condition),
                        },
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
