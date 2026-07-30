from __future__ import annotations

from concurrent.futures import Future
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType, MethodType, SimpleNamespace
from typing import Any, cast

import pytest

import orchestrator.workflow.executor as executor_module
from orchestrator.providers.interactive_terminal import InteractiveTerminalError
from orchestrator.providers.types import InteractiveSessionSupport
from orchestrator.state import RunState, StateManager, StepResult
from orchestrator.workflow.call_frame_state import (
    _CallFrameStateManager,
    _path_safe_frame_scope_token,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.provider_phased_delivery.runtime_bindings import (
    _WorkflowPhasedProviderAttemptBindings,
)
from orchestrator.workflow.executable_ir import (
    ExecutableNodeKind,
    WorkflowRegion,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    PhasedRuntimePolicy,
    ProviderBoundPolicy,
)
from orchestrator.workflow.provider_phased_delivery.bindings import (
    CandidatePathBinding,
    CandidatePreflight,
    PhasedOperationFailure,
    PhasedProviderAttemptFailure,
)
from orchestrator.workflow.provider_phased_delivery.coordinator import (
    _runtime_diagnostic,
)
from orchestrator.workflow.provider_phased_delivery.endpoint import (
    SubmitEndpointEvent,
)
from orchestrator.workflow.provider_phased_delivery.protocol import (
    SubmitRequest,
    diagnostic_from_dict,
    diagnostic_to_dict,
)
from orchestrator.workflow.prompt_dependency_evidence import evidence_relative_path
from orchestrator.workflow.provider_attempts import (
    EnclosingStep,
    ProviderAttemptScope,
)
from orchestrator.workflow.resume_projection_integrity import ResumeScopePath
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.state_projection import (
    CompatibilityNodeProjection,
    WorkflowStateProjection,
)


def _executor() -> WorkflowExecutor:
    executor = object.__new__(WorkflowExecutor)
    executor.current_step = 0
    executor.state_manager = SimpleNamespace()
    executor._contract_violation_result = MethodType(
        lambda self, message, context=None: {
            "status": "failed",
            "exit_code": 2,
            "error": {
                "type": "contract_violation",
                "message": message,
                "context": context or {},
            },
        },
        executor,
    )
    executor._create_provider_context = MethodType(
        lambda self, context, state, **kwargs: dict(context),
        executor,
    )
    executor._resolve_provider_name_for_step = MethodType(
        lambda self, step, context: (step.get("provider"), None),
        executor,
    )
    executor._compiled_frontend_origin_for_step = MethodType(
        lambda self, step_name, step_id, **kwargs: {
            "path": "workflows/review.orc",
            "line": 8,
            "column": 1,
            "end_line": 14,
            "end_column": 2,
        },
        executor,
    )
    return executor


def _exact_diagnostic(result: dict[str, Any]) -> dict[str, Any]:
    diagnostic = result["error"]["context"]["diagnostic"]
    assert diagnostic_from_dict(diagnostic).reason == diagnostic["reason"]
    assert tuple(diagnostic) == (
        "schema_version",
        "code",
        "reason",
        "rejected_value",
        "primary_source",
        "related_sources",
    )
    return diagnostic


def _support(
    schema_version: str = "interactive_terminal_turn_queue.v1",
) -> InteractiveSessionSupport:
    return InteractiveSessionSupport(
        schema_version=schema_version,
        turn_boundary_messages=True,
        command=("provider", "${PROMPT}"),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )


def test_explicit_composed_and_omitted_delivery_keep_the_ordinary_route() -> None:
    executor = _executor()
    calls: list[ProviderBoundPolicy] = []

    def ordinary(
        self,
        step,
        context,
        state,
        runtime_step_id=None,
        parent_steps=None,
        self_steps=None,
        root_steps=None,
        *,
        provider_bound_policy,
    ):
        calls.append(provider_bound_policy)
        return {"status": "completed", "exit_code": 0}

    executor._execute_composed_provider_with_context = MethodType(
        ordinary,
        executor,
    )

    for policy in (
        {"model": "m", "effort": "high"},
        {"model": "m", "effort": "high", "delivery": "composed"},
    ):
        result = executor._execute_provider_with_context(
            {"name": "review", "provider_call_policy": policy},
            {},
            {},
        )
        assert result["status"] == "completed"

    assert calls == [
        ProviderBoundPolicy(model="m", effort="high"),
        ProviderBoundPolicy(model="m", effort="high"),
    ]


def test_explicit_phased_partitions_runtime_policy_before_coordinator() -> None:
    executor = _executor()
    provider = SimpleNamespace(interactive_session_support=_support())
    executor.provider_registry = SimpleNamespace(get=lambda name: provider)
    executor.variable_substitutor = SimpleNamespace(
        substitute=lambda value, context: value
    )
    captured: list[tuple[ProviderBoundPolicy, PhasedRuntimePolicy]] = []

    def phased(
        self,
        step,
        context,
        state,
        *,
        provider_bound_policy,
        runtime_policy,
        runtime_step_id=None,
        parent_steps=None,
        self_steps=None,
        root_steps=None,
    ):
        captured.append((provider_bound_policy, runtime_policy))
        return {"status": "completed", "exit_code": 0}

    executor._execute_phased_provider_with_context = MethodType(phased, executor)
    result = executor._execute_provider_with_context(
        {
            "name": "review",
            "provider": "codex",
            "provider_call_policy": {
                "model": "m",
                "effort": "high",
                "delivery": "phased",
                "materialization_attempts": 3,
            },
        },
        {},
        {},
    )

    assert result["status"] == "completed"
    assert captured == [
        (
            ProviderBoundPolicy(model="m", effort="high"),
            PhasedRuntimePolicy(
                delivery="phased",
                materialization_attempts=3,
            ),
        )
    ]


@pytest.mark.parametrize(
    ("support", "expected_code", "expected_reason", "canonical_value"),
    [
        (
            None,
            "provider_phased_interactive_capability_missing",
            "interactive_capability_absent",
            None,
        ),
        (
            _support("interactive_terminal_turn_queue.v2"),
            "provider_phased_interactive_capability_invalid",
            "interactive_capability_schema_unsupported",
            None,
        ),
        (
            InteractiveSessionSupport(
                schema_version="interactive_terminal_turn_queue.v1",
                turn_boundary_messages=False,
                command=("provider", "${PROMPT}"),
                message_submit_keys=("ENTER",),
                graceful_close_text="/exit",
                graceful_close_submit_keys=("ENTER",),
            ),
            "provider_phased_interactive_capability_invalid",
            "turn_boundary_messages_not_true",
            False,
        ),
        (
            InteractiveSessionSupport(
                schema_version="interactive_terminal_turn_queue.v1",
                turn_boundary_messages=True,
                command=(),
                message_submit_keys=("ENTER",),
                graceful_close_text="/exit",
                graceful_close_submit_keys=("ENTER",),
            ),
            "provider_phased_interactive_capability_invalid",
            "interactive_capability_malformed",
            None,
        ),
    ],
    ids=(
        "absent",
        "schema-unsupported",
        "turn-boundary-false",
        "structurally-malformed",
    ),
)
def test_phased_capability_drift_refuses_before_every_runtime_action(
    support: InteractiveSessionSupport | None,
    expected_code: str,
    expected_reason: str,
    canonical_value: bool | None,
) -> None:
    executor = _executor()
    provider = SimpleNamespace(
        interactive_session_support=support
    )
    executor.provider_registry = SimpleNamespace(get=lambda name: provider)
    executor.variable_substitutor = SimpleNamespace(
        substitute=lambda value, context: value
    )
    calls: list[str] = []
    executor._execute_phased_provider_with_context = MethodType(
        lambda self, *args, **kwargs: calls.append("phased-route"),
        executor,
    )
    executor._execute_composed_provider_with_context = MethodType(
        lambda self, *args, **kwargs: calls.append("composed-route"),
        executor,
    )
    executor._build_phased_provider_attempt_bindings = MethodType(
        lambda self, **kwargs: calls.append("binding-allocation"),
        executor,
    )
    executor._run_phased_provider_attempt = MethodType(
        lambda self, bindings: calls.append("coordinator"),
        executor,
    )
    executor.provider_executor = SimpleNamespace(
        prepare_interactive_invocation=lambda **kwargs: calls.append(
            "provider-start"
        )
    )

    result = executor._execute_provider_with_context(
        {
            "name": "review",
            "provider": "codex",
            "provider_call_policy": {
                "delivery": "phased",
                "materialization_attempts": 2,
            },
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == expected_code
    assert result["error"]["context"]["reason"] == expected_reason
    assert result["error"]["context"]["rejected_value"]["summary"] == (
        expected_reason
    )
    assert result["error"]["context"]["rejected_value"][
        "canonical_value"
    ] == canonical_value
    diagnostic = _exact_diagnostic(result)
    assert diagnostic["code"] == expected_code
    assert diagnostic["reason"] == expected_reason
    assert diagnostic["rejected_value"] == result["error"]["context"][
        "rejected_value"
    ]
    assert diagnostic["primary_source"] == {
        "kind": "provider_template",
        "owner": "resolved_provider_template",
        "path": None,
        "span": None,
    }
    assert diagnostic["related_sources"] == [
        {
            "kind": "authored_span",
            "owner": "provider_application",
            "path": "workflows/review.orc",
            "span": {
                "start_line": 8,
                "start_column": 1,
                "end_line": 14,
                "end_column": 2,
            },
        }
    ]
    assert calls == []


def test_phased_binding_preparation_failure_uses_closed_refusal_without_fallback(
) -> None:
    executor = _executor()
    calls: list[str] = []

    def fail_binding(self, **kwargs):
        calls.append("binding-preparation")
        raise ValueError("binding preparation failed")

    executor._build_phased_provider_attempt_bindings = MethodType(
        fail_binding,
        executor,
    )
    executor._run_phased_provider_attempt = MethodType(
        lambda self, bindings: calls.append("coordinator"),
        executor,
    )
    executor._execute_composed_provider_with_context = MethodType(
        lambda self, *args, **kwargs: calls.append("composed-route"),
        executor,
    )

    result = executor._execute_phased_provider_with_context(
        {"name": "review"},
        {},
        {},
        provider_bound_policy=ProviderBoundPolicy(model="m"),
        runtime_policy=PhasedRuntimePolicy(
            delivery="phased",
            materialization_attempts=2,
        ),
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_phased_preparation_failed"
    assert result["error"]["context"]["reason"] == "preparation_failed"
    assert result["error"]["context"]["rejected_value"]["summary"] == (
        "preparation_failed"
    )
    assert result["error"]["context"]["error"] == (
        "binding preparation failed"
    )
    diagnostic = _exact_diagnostic(result)
    assert diagnostic["reason"] == "preparation_failed"
    assert diagnostic["primary_source"] == {
        "kind": "runtime_attempt",
        "owner": "candidate_set",
        "path": None,
        "span": None,
    }
    assert [
        source["owner"] for source in diagnostic["related_sources"]
    ] == ["runtime_step", "phase_lifecycle"]
    assert calls == ["binding-preparation"]


def test_phased_coordinator_exception_is_not_a_preparation_refusal() -> None:
    executor = _executor()
    binding = SimpleNamespace(runtime_result=lambda result: result)
    executor._build_phased_provider_attempt_bindings = MethodType(
        lambda self, **kwargs: binding,
        executor,
    )
    executor._run_phased_provider_attempt = MethodType(
        lambda self, candidate: (_ for _ in ()).throw(
            RuntimeError("coordinator escaped")
        ),
        executor,
    )

    with pytest.raises(RuntimeError, match="coordinator escaped"):
        executor._execute_phased_provider_with_context(
            {"name": "review"},
            {},
            {},
            provider_bound_policy=ProviderBoundPolicy(model="m"),
            runtime_policy=PhasedRuntimePolicy(
                delivery="phased",
                materialization_attempts=2,
            ),
        )


def test_closed_policy_refusal_has_zero_runtime_route_calls() -> None:
    executor = _executor()
    calls: list[str] = []
    executor._execute_phased_provider_with_context = MethodType(
        lambda self, *args, **kwargs: calls.append("phased"),
        executor,
    )
    executor._execute_composed_provider_with_context = MethodType(
        lambda self, *args, **kwargs: calls.append("composed"),
        executor,
    )

    result = executor._execute_provider_with_context(
        {
            "name": "review",
            "provider_call_policy": {
                "delivery": "phased",
                "materialization_attempts": 2,
                "future_runtime_option": "not-open",
            },
        },
        {},
        {},
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_phased_delivery_carriage_mismatch"
    )
    assert result["error"]["context"]["reason"] == (
        "call_policy_carriage_extra"
    )
    assert result["error"]["context"]["rejected_value"]["summary"] == (
        "call_policy_carriage_extra"
    )
    diagnostic = _exact_diagnostic(result)
    assert diagnostic["reason"] == "call_policy_carriage_extra"
    assert diagnostic["primary_source"]["owner"] == "runtime_step"
    assert [
        source["owner"] for source in diagnostic["related_sources"]
    ] == [
        "provider_call_policy",
        "semantic_ir",
        "executable_ir",
        "persisted_provider_config",
        "lexical_checkpoint",
    ]
    assert all(
        source["kind"] == "carrier_boundary"
        and source["path"] == "workflows/review.orc"
        for source in (
            *diagnostic["related_sources"],
            diagnostic["primary_source"],
        )
    )
    assert calls == []


def test_phased_route_constructs_bindings_and_runs_only_the_task10_coordinator() -> None:
    executor = _executor()
    binding = SimpleNamespace(
        runtime_result=lambda result: {
            "status": "completed",
            "exit_code": 0,
            "coordinator_result": result,
        }
    )
    captured: list[object] = []

    def build(self, **kwargs):
        captured.append(kwargs)
        return binding

    def run(self, candidate):
        captured.append(candidate)
        return "task10-complete"

    executor._build_phased_provider_attempt_bindings = MethodType(
        build,
        executor,
    )
    executor._run_phased_provider_attempt = MethodType(run, executor)

    result = executor._execute_phased_provider_with_context(
        {"name": "review"},
        {},
        {},
        provider_bound_policy=ProviderBoundPolicy(model="m"),
        runtime_policy=PhasedRuntimePolicy(
            delivery="phased",
            materialization_attempts=2,
        ),
    )

    assert captured[-1] is binding
    assert captured[0]["provider_bound_policy"] == ProviderBoundPolicy(model="m")
    assert captured[0]["runtime_policy"] == PhasedRuntimePolicy(
        delivery="phased",
        materialization_attempts=2,
    )
    assert result["coordinator_result"] == "task10-complete"


@pytest.mark.parametrize("code", ["pane_lost", "pane_status_invalid"])
def test_phased_liveness_probe_loss_serializes_provider_exit(code: str) -> None:
    class EmptyEndpoint:
        def receive_event(self, *, deadline: float):
            raise TimeoutError

    class LostAdapter:
        def probe_process_status(self, *, deadline: float):
            raise InteractiveTerminalError(code)

    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    cast(Any, binding).adapter = LostAdapter()

    event = binding.receive_attempt_event(
        boundary="AWAITING_SUBMIT",
        endpoint=EmptyEndpoint(),
        deadline=10**18,
    )

    assert event is not None
    assert event.kind == "provider_exit"
    assert event.submit is None


def test_phased_liveness_probe_timeout_is_sliced_and_rechecks_submit(
    monkeypatch,
) -> None:
    request = SubmitRequest(
        attempt_scope_sha256="sha256:" + "a" * 64,
        endpoint_instance_id="endpoint",
        binding_token="b" * 64,
        client_request_id="request",
        payload_sha256="sha256:" + "c" * 64,
    )
    submit = SubmitEndpointEvent(
        request=request,
        submission_ordinal=1,
        _waiter=Future(),
        _response_sent=Future(),
    )

    class ArrivingEndpoint:
        calls = 0

        def receive_event(self, *, deadline: float):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError
            return submit

    class SlicedTimeoutAdapter:
        deadlines: list[float] = []

        def probe_process_status(self, *, deadline: float):
            self.deadlines.append(deadline)
            raise InteractiveTerminalError("backend_operation_timeout")

    monkeypatch.setattr(
        "orchestrator.workflow.provider_phased_delivery.runtime_bindings.time.monotonic",
        lambda: 100.0,
    )
    endpoint = ArrivingEndpoint()
    adapter = SlicedTimeoutAdapter()
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    cast(Any, binding).adapter = adapter

    event = binding.receive_attempt_event(
        boundary="AWAITING_SUBMIT",
        endpoint=endpoint,
        deadline=101.0,
    )

    assert event is not None
    assert event.kind == "submit"
    assert event.submit is submit
    assert endpoint.calls == 2
    assert adapter.deadlines == [100.05]


def test_phased_submit_wait_reports_whole_attempt_deadline(
    monkeypatch,
) -> None:
    class EmptyEndpoint:
        def receive_event(self, *, deadline: float):
            raise TimeoutError

    class UnusedAdapter:
        def probe_process_status(self, *, deadline: float):
            raise AssertionError("expired whole deadline must not probe")

    clock = iter((99.95, 100.0))
    monkeypatch.setattr(
        "orchestrator.workflow.provider_phased_delivery.runtime_bindings.time.monotonic",
        lambda: next(clock),
    )
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    cast(Any, binding).adapter = UnusedAdapter()

    event = binding.receive_attempt_event(
        boundary="AWAITING_SUBMIT",
        endpoint=EmptyEndpoint(),
        deadline=100.0,
    )

    assert event is not None
    assert event.kind == "deadline"
    assert event.submit is None


def test_interrupted_phased_visit_reruns_from_task_turn_with_fresh_attempt() -> None:
    executor = _executor()
    executor._step_node_ids = ["root.review"]
    executor._runtime_step_for_node_id = MethodType(
        lambda self, node_id: {
            "name": "review",
            "provider_call_policy": {
                "delivery": "phased",
                "materialization_attempts": 2,
            }
        },
        executor,
    )
    executor._execution_kind_for_step = MethodType(
        lambda self, step: ExecutableNodeKind.PROVIDER,
        executor,
    )
    executor._step_id = MethodType(
        lambda self, step, fallback_index=None: "root.review",
        executor,
    )

    guard = executor._interrupted_phased_provider_guard(
        {
            "current_step": {
                "name": "review",
                "index": 0,
                "type": "provider",
                "status": "running",
                "step_id": "root.review",
                "visit_count": 1,
            }
        }
    )

    assert guard == {
        "kind": "rerun_interrupted_visit",
        "step_name": "review",
        "step_id": "root.review",
        "visit_count": 1,
        "node_id": "root.review",
    }


def test_existing_phased_quarantine_is_sticky_after_current_step_is_cleared(
) -> None:
    executor = _executor()
    executor._step_node_ids = []
    error = {
        "type": "provider_phased_interrupted_visit_quarantined",
        "message": "sticky",
        "context": {"step_id": "root.review", "visit_count": 1},
    }
    state = {
        "status": "failed",
        "current_step": None,
        "error": error,
    }

    assert executor._interrupted_phased_provider_guard(state) == {
        "kind": "existing_quarantine",
        "error": error,
    }
    assert state["error"] is error


def test_cleared_current_step_without_phased_quarantine_is_not_claimed() -> None:
    executor = _executor()
    executor._step_node_ids = []

    assert (
        executor._interrupted_phased_provider_guard(
            {
                "status": "failed",
                "current_step": None,
                "error": {
                    "type": "some_other_failure",
                    "message": "unrelated",
                },
            }
        )
        is None
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "other"),
        ("type", "command"),
        ("status", "completed"),
        ("step_id", "root.other"),
        ("index", 1),
        ("index", "0"),
        ("visit_count", 0),
        ("visit_count", True),
    ],
)
def test_interrupted_phased_visit_malformed_cursor_fails_integrity(
    field: str,
    value: object,
) -> None:
    executor = _executor()
    executor._step_node_ids = ["root.review"]
    executor._runtime_step_for_node_id = MethodType(
        lambda self, node_id: {
            "name": "review",
            "provider_call_policy": {
                "delivery": "phased",
                "materialization_attempts": 2,
            },
        },
        executor,
    )
    executor._execution_kind_for_step = MethodType(
        lambda self, step: ExecutableNodeKind.PROVIDER,
        executor,
    )
    executor._step_id = MethodType(
        lambda self, step, fallback_index=None: "root.review",
        executor,
    )
    current_step = {
        "name": "review",
        "index": 0,
        "type": "provider",
        "status": "running",
        "step_id": "root.review",
        "visit_count": 1,
    }
    current_step[field] = value

    guard = executor._interrupted_phased_provider_guard(
        {"current_step": current_step}
    )

    assert guard is not None
    assert guard["kind"] == "integrity_error"
    assert guard["context"]["current_step"] == current_step


def test_completed_phased_result_needs_no_provider_endpoint_or_ledger_read() -> None:
    executor = _executor()
    executor._step_node_ids = ["root.review"]
    executor._runtime_step_for_node_id = MethodType(
        lambda self, node_id: (_ for _ in ()).throw(
            AssertionError("completed reuse inspected RuntimeStep")
        ),
        executor,
    )

    assert (
        executor._interrupted_phased_provider_guard(
            {
                "current_step": None,
                "steps": {
                    "review": {
                        "status": "completed",
                        "exit_code": 0,
                    }
                },
            }
        )
        is None
    )


def _completed_phased_resume_seam(
    tmp_path,
    *,
    count: int = 1,
) -> tuple[WorkflowExecutor, dict[str, Any]]:
    executor = _executor()
    (tmp_path / "workflow.orc").write_text(
        "(workflow :version 1)\n",
        encoding="utf-8",
    )
    manager = StateManager(tmp_path, run_id="completed-boundary")
    manager.initialize("workflow.orc")
    executor.state_manager = manager
    executor.resume_planner = ResumePlanner()
    node_ids = [f"root.review_{index}" for index in range(count)]
    executor._step_node_ids = cast(list[str | None], node_ids)
    steps_by_node_id = {
        node_id: {
            "name": f"review_{index}",
            "provider_call_policy": {
                "delivery": "phased",
                "materialization_attempts": 2,
            },
        }
        for index, node_id in enumerate(node_ids)
    }
    entries = {
        node_id: CompatibilityNodeProjection(
            node_id=node_id,
            step_id=node_id,
            presentation_key=f"review_{index}",
            display_name=f"review_{index}",
            region=WorkflowRegion.BODY,
            compatibility_index=index,
        )
        for index, node_id in enumerate(node_ids)
    }
    executor.projection = WorkflowStateProjection(
        entries_by_node_id=MappingProxyType(entries),
        node_id_by_compatibility_index=MappingProxyType(
            {
                index: node_id
                for index, node_id in enumerate(node_ids)
            }
        ),
        compatibility_index_by_node_id=MappingProxyType(
            {
                node_id: index
                for index, node_id in enumerate(node_ids)
            }
        ),
        presentation_key_by_node_id=MappingProxyType(
            {
                node_id: f"review_{index}"
                for index, node_id in enumerate(node_ids)
            }
        ),
        node_id_by_step_id=MappingProxyType(
            {node_id: node_id for node_id in node_ids}
        ),
    )
    executor._runtime_step_for_node_id = MethodType(
        lambda self, node_id: steps_by_node_id[node_id],
        executor,
    )
    executor._execution_kind_for_step = MethodType(
        lambda self, step: ExecutableNodeKind.PROVIDER,
        executor,
    )
    executor._step_id = MethodType(
        lambda self, step, fallback_index=None: node_ids[
            next(
                index
                for index, candidate in enumerate(steps_by_node_id.values())
                if candidate is step
            )
        ],
        executor,
    )
    state: dict[str, Any] = {
        "run_id": "completed-boundary",
        "workflow_file": "workflow.orc",
        "status": "failed",
        "current_step": None,
        "steps": {},
        "step_visits": {},
        "provider_attempt_allocations": {},
    }
    for index, node_id in enumerate(node_ids):
        step_name = f"review_{index}"
        scope = ProviderAttemptScope(
            run_id="completed-boundary",
            resume_scope=ResumeScopePath.root("workflow.orc"),
            runtime_step_id=node_id,
            enclosing_step=EnclosingStep(
                step_name=step_name,
                step_id=node_id,
                visit_count=1,
            ),
            loop_iteration=None,
            adjudication_subject=None,
        )
        evidence_path = str(evidence_relative_path(scope, 1))
        state["steps"][step_name] = {
            "status": "completed",
            "exit_code": 0,
            "name": step_name,
            "step_id": node_id,
            "visit_count": 1,
            "artifacts": {"approved": True},
            "debug": {
                "phased_delivery": {
                    "submission_ordinal": 2,
                    "functional_evidence": evidence_path,
                }
            },
        }
        state["step_visits"][step_name] = 1
        state["provider_attempt_allocations"][scope.key] = {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 1,
            "events": [
                {"ordinal": 1, "event": "allocated"},
                {
                    "ordinal": 1,
                    "event": "evidence_published",
                    "relative_path": evidence_path,
                    "file_sha256": "sha256:" + f"{index + 1:064x}",
                    "record_kind": "prompt_snapshot",
                },
            ],
            "prompt_fragment_identity_schema_version": (
                "compiled_prompt_fragment_identity.v2"
            ),
        }
    assert manager.state is not None
    manager.state.status = "failed"
    manager.state.current_step = None
    manager.state.steps = deepcopy(state["steps"])
    manager.state.step_visits = deepcopy(state["step_visits"])
    manager.state.provider_attempt_allocations = deepcopy(
        state["provider_attempt_allocations"]
    )
    return executor, manager.state.to_dict()


def test_completed_phased_resume_boundary_reuses_exact_state_authority(
    tmp_path,
) -> None:
    executor, state = _completed_phased_resume_seam(tmp_path)

    assessment = executor._completed_phased_provider_resume_boundary(state)

    assert assessment == {
        "kind": "reuse",
        "boundaries": [
            {
                "node_id": "root.review_0",
                "step_name": "review_0",
                "step_id": "root.review_0",
                "visit_count": 1,
                "evidence_sha256": "sha256:" + f"{1:064x}",
            }
        ],
    }


@pytest.mark.parametrize(
    ("tamper", "reason"),
    [
        ("missing_evidence", "completed_phased_evidence_missing"),
        ("step_id", "completed_phased_result_identity_mismatch"),
        ("nonterminal", "completed_phased_state_incomplete"),
    ],
)
def test_completed_phased_resume_boundary_fails_closed_on_invalid_authority(
    tmp_path,
    tamper: str,
    reason: str,
) -> None:
    executor, state = _completed_phased_resume_seam(
        tmp_path,
        count=2 if tamper == "nonterminal" else 1,
    )
    if tamper == "missing_evidence":
        allocation = next(iter(state["provider_attempt_allocations"].values()))
        allocation["events"] = [{"ordinal": 1, "event": "allocated"}]
    elif tamper == "step_id":
        state["steps"]["review_0"]["step_id"] = "root.tampered"
    elif tamper == "nonterminal":
        state["steps"]["review_1"]["status"] = "running"
    executor.state_manager.state = RunState.from_dict(state)

    assessment = executor._completed_phased_provider_resume_boundary(state)

    assert assessment["kind"] == "integrity_error"
    assert assessment["reason"] == reason


def test_completed_phased_resume_boundary_rejects_duplicate_evidence_authority(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, state = _completed_phased_resume_seam(tmp_path)
    allocation = next(
        iter(state["provider_attempt_allocations"].values())
    )
    monkeypatch.setattr(
        executor_module,
        "validate_provider_attempt_allocations",
        lambda value: {
            "first": allocation,
            "duplicate": deepcopy(allocation),
        },
    )

    assessment = executor._completed_phased_provider_resume_boundary(state)

    assert assessment["kind"] == "integrity_error"
    assert assessment["reason"] == "completed_phased_evidence_ambiguous"
    assert assessment["match_count"] == 2


def test_completed_phased_resume_allows_absent_unselected_projected_node(
    tmp_path,
) -> None:
    executor, state = _completed_phased_resume_seam(tmp_path, count=2)
    state["steps"].pop("review_1")
    state["step_visits"].pop("review_1")
    state["provider_attempt_allocations"] = {
        key: allocation
        for key, allocation in state[
            "provider_attempt_allocations"
        ].items()
        if allocation["scope"]["runtime_step_id"] != "root.review_1"
    }
    executor.state_manager.state = RunState.from_dict(state)

    assessment = executor._completed_phased_provider_resume_boundary(state)

    assert assessment == {
        "kind": "reuse",
        "boundaries": [
            {
                "node_id": "root.review_0",
                "step_name": "review_0",
                "step_id": "root.review_0",
                "visit_count": 1,
                "evidence_sha256": "sha256:" + f"{1:064x}",
            }
        ],
    }


def test_two_completed_phased_boundaries_reuse_and_skip_execution(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor, state = _completed_phased_resume_seam(tmp_path, count=2)
    assessment = executor._completed_phased_provider_resume_boundary(state)
    executor._determine_resume_restart_node_id = MethodType(
        lambda self, current: None,
        executor,
    )
    executor._determine_resume_default_resume_decision = MethodType(
        lambda self, current: {
            "mode": "NO_RESTART",
            "restore_decision": None,
        },
        executor,
    )
    executor._write_default_resume_report = MethodType(
        lambda self, decision: None,
        executor,
    )
    executor._first_execution_node_id = MethodType(
        lambda self: (_ for _ in ()).throw(
            AssertionError("completed reuse selected provider execution")
        ),
        executor,
    )
    executor._build_phased_provider_attempt_bindings = MethodType(
        lambda self, **kwargs: (_ for _ in ()).throw(
            AssertionError("completed reuse constructed an endpoint")
        ),
        executor,
    )
    original_open = Path.open

    def reject_phase_ledger(path: Path, *args: Any, **kwargs: Any):
        if path.name.endswith("-provider-prompt-phases.jsonl"):
            raise AssertionError("completed reuse opened phased ledger")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", reject_phase_ledger)

    loop_result = executor._execute_step_loop(
        state,
        resume=True,
        on_error="stop",
        terminal_status="completed",
        completed_phased_resume_boundary=assessment,
    )

    assert assessment == {
        "kind": "reuse",
        "boundaries": [
            {
                "node_id": "root.review_0",
                "step_name": "review_0",
                "step_id": "root.review_0",
                "visit_count": 1,
                "evidence_sha256": "sha256:" + f"{1:064x}",
            },
            {
                "node_id": "root.review_1",
                "step_name": "review_1",
                "step_id": "root.review_1",
                "visit_count": 1,
                "evidence_sha256": "sha256:" + f"{2:064x}",
            },
        ],
    }
    assert loop_result.terminal_status == "completed"
    assert loop_result.early_result is None


def test_atomic_commit_guard_rejection_leaks_no_live_success_projection() -> None:
    live_state = {
        "steps": {},
        "artifact_versions": {},
        "artifact_consumes": {},
        "private_artifact_versions": {},
        "private_artifact_consumes": {},
    }
    before = {
        key: dict(value)
        for key, value in live_state.items()
    }

    class RejectingManager:
        state = SimpleNamespace(
            current_step={
                "name": "review",
                "type": "provider",
                "status": "running",
                "step_id": "different",
                "visit_count": 1,
            }
        )

        def finalize_step_with_dataflow(self, *args, commit_guard, **kwargs):
            assert commit_guard() is True
            raise TimeoutError("rejected")

    executor = _executor()
    executor.state_manager = RejectingManager()
    executor._to_step_result = MethodType(
        lambda self, result, name: result,
        executor,
    )
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step_name = "review"
    binding.state = live_state
    binding._prepared_result = {
        "status": "completed",
        "exit_code": 0,
        "step_id": "root.review",
    }
    binding._prepared_state = {
        **before,
        "steps": {"review": binding._prepared_result},
    }
    binding._prepared_visit_count = 1
    prepared = SimpleNamespace(
        allocation=SimpleNamespace(
            scope=SimpleNamespace(
                enclosing_step=SimpleNamespace(
                    step_name="review",
                    step_id="root.review",
                    visit_count=1,
                ),
                loop_iteration=None,
            )
        ),
        evidence=SimpleNamespace(evidence_sha256="sha256:" + "a" * 64),
        frozen=SimpleNamespace(frozen_sha256="sha256:" + "b" * 64),
    )

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.atomic_success_commit(prepared, deadline=10**18)

    assert raised.value.diagnostic.reason == "workflow_state_commit_failed"
    assert live_state == before
    assert not hasattr(executor, "_phased_authoritative_result_ids")


def test_atomic_commit_guard_rejection_preserves_exact_disk_and_lineage(
    tmp_path,
) -> None:
    workflow_file = tmp_path / "workflow.orc"
    workflow_file.write_text("(workflow :version 1)\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="phased-atomic-negative")
    manager.initialize("workflow.orc")
    manager.start_step(
        "review",
        0,
        "provider",
        step_id="different",
        visit_count=1,
    )
    assert manager.state is not None
    disk_before = manager.state_file.read_bytes()
    live_before = manager.state.to_dict()

    executor = _executor()
    executor.state_manager = manager
    executor._to_step_result = MethodType(
        lambda self, result, name: result,
        executor,
    )
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step_name = "review"
    binding.state = deepcopy(live_before)
    binding._prepared_result = {
        "status": "completed",
        "exit_code": 0,
        "step_id": "root.review",
    }
    binding._prepared_state = {
        **deepcopy(live_before),
        "steps": {"review": binding._prepared_result},
        "artifact_versions": {
            "report": [
                {
                    "step_name": "review",
                    "version": 1,
                    "path": "artifacts/report.md",
                }
            ]
        },
    }
    binding._prepared_visit_count = 1
    prepared = SimpleNamespace(
        allocation=SimpleNamespace(
            scope=SimpleNamespace(
                enclosing_step=SimpleNamespace(
                    step_name="review",
                    step_id="root.review",
                    visit_count=1,
                ),
                loop_iteration=None,
            )
        ),
        evidence=SimpleNamespace(evidence_sha256="sha256:" + "a" * 64),
        frozen=SimpleNamespace(frozen_sha256="sha256:" + "b" * 64),
    )

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.atomic_success_commit(prepared, deadline=10**18)

    assert raised.value.diagnostic.reason == "workflow_state_commit_failed"
    assert manager.state_file.read_bytes() == disk_before
    assert manager.state is not None
    assert manager.state.to_dict() == live_before
    assert binding.state == live_before
    assert not hasattr(executor, "_phased_authoritative_result_ids")


def _call_frame_manager(tmp_path):
    workflow_file = tmp_path / "workflow.orc"
    workflow_file.write_text("(workflow :version 1)\n", encoding="utf-8")
    root = StateManager(tmp_path, run_id="phased-call-frame")
    root.initialize("workflow.orc")
    frame_id = "root.call::visit::1"
    frame_root = (
        root.run_root / "call_frames" / _path_safe_frame_scope_token(frame_id)
    )
    now = datetime.now(timezone.utc).isoformat()
    child_state = RunState(
        schema_version=StateManager.SCHEMA_VERSION,
        run_id=root.run_id,
        workflow_file="child.orc",
        workflow_checksum="sha256:" + "c" * 64,
        started_at=now,
        updated_at=now,
        status="running",
        run_root=str(frame_root),
        current_step={
            "name": "Review",
            "index": 0,
            "type": "provider",
            "status": "running",
            "step_id": "child.review",
            "visit_count": 1,
        },
        step_visits={"Review": 1},
    )
    child = object.__new__(_CallFrameStateManager)
    child.parent_manager = root
    child.workspace = root.workspace
    child.frame_id = frame_id
    child.resume_scope_path = ResumeScopePath(
        "workflow.orc",
        (frame_id,),
    )
    child.run_id = root.run_id
    child.run_root = frame_root
    child.state = child_state
    root.update_call_frame(
        frame_id,
        {
            "call_frame_id": frame_id,
            "call_step_name": "Call",
            "call_step_id": "root.call",
            "import_alias": "child",
            "workflow_file": "child.orc",
            "status": "running",
            "body_status": None,
            "finalization_status": "not_configured",
            "export_status": "not_configured",
            "bound_inputs": {},
            "bound_input_resume_validation": {
                "status": "fresh",
                "diagnostics": [],
            },
            "current_step": child_state.current_step,
            "state": child_state.to_dict(),
        },
    )
    return root, child


def test_call_frame_phased_commit_is_one_guarded_root_state_write(
    tmp_path,
) -> None:
    root, child = _call_frame_manager(tmp_path)
    executor = _executor()
    executor.state_manager = child
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step_name = "Review"
    binding.state = child.state.to_dict()
    binding._prepared_result = {
        "status": "completed",
        "name": "Review",
        "step_id": "child.review",
        "exit_code": 0,
        "visit_count": 1,
    }
    binding._prepared_state = {
        **deepcopy(binding.state),
        "steps": {"Review": binding._prepared_result},
        "artifact_versions": {
            "report": [
                {
                    "version": 1,
                    "producer": "child.review",
                }
            ]
        },
    }
    binding._prepared_visit_count = 1
    prepared = SimpleNamespace(
        allocation=SimpleNamespace(
            scope=SimpleNamespace(
                enclosing_step=SimpleNamespace(
                    step_name="Review",
                    step_id="child.review",
                    visit_count=1,
                ),
                loop_iteration=None,
            )
        ),
        evidence=SimpleNamespace(evidence_sha256="sha256:" + "a" * 64),
        frozen=SimpleNamespace(frozen_sha256="sha256:" + "b" * 64),
    )

    binding.atomic_success_commit(prepared, deadline=10**18)

    persisted = StateManager(
        tmp_path,
        run_id=root.run_id,
    ).load().call_frames[child.frame_id]["state"]
    assert "current_step" not in persisted
    assert persisted["steps"]["Review"]["status"] == "completed"
    assert persisted["artifact_versions"]["report"][0]["producer"] == (
        "child.review"
    )
    assert child.state.to_dict() == persisted


def test_call_frame_phased_guard_rejection_leaks_no_disk_or_lineage(
    tmp_path,
) -> None:
    root, child = _call_frame_manager(tmp_path)
    disk_before = root.state_file.read_bytes()
    child_before = child.state.to_dict()

    with pytest.raises(TimeoutError, match="state commit guard"):
        child.finalize_step_with_dataflow(
            "Review",
            StepResult(
                status="completed",
                name="Review",
                step_id="child.review",
                exit_code=0,
                visit_count=1,
            ),
            artifact_versions={
                "report": [{"version": 1, "producer": "child.review"}]
            },
            expected_step_id="child.other",
            expected_visit_count=1,
            expected_step_name="Review",
            expected_step_type="provider",
            expected_step_status="running",
            commit_guard=lambda: True,
        )

    assert root.state_file.read_bytes() == disk_before
    assert child.state.to_dict() == child_before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Other"),
        ("type", "command"),
        ("status", "completed"),
    ],
)
def test_call_frame_phased_guard_rejects_authoritative_leaf_tamper(
    tmp_path,
    field: str,
    value: str,
) -> None:
    root, child = _call_frame_manager(tmp_path)
    assert root.state is not None
    frame = deepcopy(root.state.call_frames[child.frame_id])
    frame["state"]["current_step"][field] = value
    frame["current_step"][field] = value
    root.update_call_frame(child.frame_id, frame)
    assert child.state.current_step is not None
    child.state.current_step[field] = value
    disk_before = root.state_file.read_bytes()
    cached_before = child.state.to_dict()

    with pytest.raises(TimeoutError, match="state commit guard"):
        child.finalize_step_with_dataflow(
            "Review",
            StepResult(
                status="completed",
                name="Review",
                step_id="child.review",
                exit_code=0,
                visit_count=1,
            ),
            expected_step_id="child.review",
            expected_visit_count=1,
            expected_step_name="Review",
            expected_step_type="provider",
            expected_step_status="running",
            commit_guard=lambda: True,
        )

    assert root.state_file.read_bytes() == disk_before
    assert child.state.to_dict() == cached_before


def test_nested_loop_phased_commit_preserves_enclosing_visit(
    tmp_path,
) -> None:
    workflow_file = tmp_path / "workflow.orc"
    workflow_file.write_text("(workflow :version 1)\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="phased-loop")
    manager.initialize("workflow.orc")
    manager.start_step(
        "Loop",
        0,
        "for_each",
        step_id="root.loop",
        visit_count=1,
    )
    assert manager.state is not None
    executor = _executor()
    executor.state_manager = manager
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step_name = "Review"
    binding.state = manager.state.to_dict()
    binding._prepared_result = {
        "status": "completed",
        "name": "Review",
        "step_id": "root.loop#0.review",
        "exit_code": 0,
        "visit_count": 1,
    }
    binding._prepared_state = {
        **deepcopy(binding.state),
        "steps": {
            "Loop[0].Review": binding._prepared_result,
        },
        "artifact_versions": {
            "report": [
                {
                    "version": 1,
                    "producer": "root.loop#0.review",
                }
            ]
        },
    }
    binding._prepared_visit_count = 1
    prepared = SimpleNamespace(
        allocation=SimpleNamespace(
            scope=SimpleNamespace(
                enclosing_step=SimpleNamespace(
                    step_name="Loop",
                    step_id="root.loop",
                    visit_count=1,
                ),
                loop_iteration=SimpleNamespace(
                    kind="for_each",
                    iteration=0,
                ),
            )
        ),
        evidence=SimpleNamespace(evidence_sha256="sha256:" + "a" * 64),
        frozen=SimpleNamespace(frozen_sha256="sha256:" + "b" * 64),
    )

    binding.atomic_success_commit(prepared, deadline=10**18)

    persisted = StateManager(tmp_path, run_id=manager.run_id).load()
    assert persisted.current_step is not None
    assert persisted.current_step["step_id"] == "root.loop"
    assert persisted.steps["Loop[0].Review"]["step_id"] == (
        "root.loop#0.review"
    )
    assert persisted.artifact_versions["report"][0]["producer"] == (
        "root.loop#0.review"
    )


def test_phased_failure_runtime_result_uses_closed_diagnostic_summary() -> None:
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding._prepared_result = None
    diagnostic = _runtime_diagnostic("workflow_state_commit_failed")
    failure = object.__new__(PhasedProviderAttemptFailure)
    object.__setattr__(failure, "first_diagnostic", diagnostic)
    object.__setattr__(failure, "terminalization_tier", "T2b")

    result = binding.runtime_result(failure)

    assert result["status"] == "failed"
    assert result["error"]["type"] == diagnostic.code
    assert result["error"]["message"] == diagnostic.rejected_value.summary


@pytest.mark.parametrize(
    ("operation", "expected_reason"),
    [
        ("evidence", "evidence_publication_failed"),
        ("restoration", "frozen_restoration_failed"),
        ("verification", "frozen_verification_failed"),
        ("preparation", "workflow_state_commit_failed"),
    ],
)
def test_physical_publication_boundaries_translate_to_closed_failure(
    tmp_path,
    operation: str,
    expected_reason: str,
) -> None:
    executor = _executor()
    executor.workspace = tmp_path
    executor._resolve_workspace_path = MethodType(
        lambda self, path: None,
        executor,
    )
    executor._record_published_artifacts = MethodType(
        lambda self, *args, **kwargs: {
            "status": "failed",
            "error": {"type": "publication_rejected"},
        },
        executor,
    )
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step = {}
    binding.step_name = "Review"
    binding.runtime_step_id = "root.review"
    binding.state = {"steps": {}}
    binding._validated_artifacts = {}
    binding._validated_structured_artifacts = {}
    binding.retained_fragment_v1 = None
    frozen = SimpleNamespace(
        files=(
            SimpleNamespace(
                binding=SimpleNamespace(
                    workspace_relative_path="artifacts/result.json"
                ),
                content=b"candidate",
            ),
        ),
        manifest=SimpleNamespace(submission_ordinal=1),
    )

    with pytest.raises(PhasedOperationFailure) as raised:
        if operation == "evidence":
            binding.publish_functional_evidence(frozen, ())
        elif operation == "restoration":
            binding.restore_frozen_candidate(frozen)
        elif operation == "verification":
            binding.verify_frozen_candidate(
                frozen,
                SimpleNamespace(),
            )
        else:
            binding.prepare_success_commit(
                allocation=SimpleNamespace(),
                output=SimpleNamespace(),
                structured=SimpleNamespace(),
                frozen=frozen,
                evidence=SimpleNamespace(relative_path="evidence.json"),
                verification=SimpleNamespace(),
            )

    assert raised.value.diagnostic.reason == expected_reason


def test_physical_state_write_failure_rolls_back_live_success_and_dataflow(
    tmp_path,
    monkeypatch,
) -> None:
    workflow_file = tmp_path / "workflow.orc"
    workflow_file.write_text("(workflow :version 1)\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="phased-atomic-write-failure")
    manager.initialize("workflow.orc")
    manager.start_step(
        "Review",
        0,
        "provider",
        step_id="root.review",
        visit_count=1,
    )
    assert manager.state is not None
    disk_before = manager.state_file.read_bytes()
    live_before = manager.state.to_dict()

    executor = _executor()
    executor.state_manager = manager
    executor._to_step_result = MethodType(
        lambda self, result, name: StepResult(
            status="completed",
            name=name,
            step_id=result["step_id"],
            exit_code=0,
            visit_count=1,
        ),
        executor,
    )
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step_name = "Review"
    binding.state = deepcopy(live_before)
    binding._prepared_result = {
        "status": "completed",
        "exit_code": 0,
        "step_id": "root.review",
        "visit_count": 1,
    }
    binding._prepared_state = {
        **deepcopy(live_before),
        "steps": {"Review": binding._prepared_result},
        "artifact_versions": {
            "report": [{"version": 1, "producer": "root.review"}]
        },
    }
    binding._prepared_visit_count = 1
    prepared = SimpleNamespace(
        allocation=SimpleNamespace(
            scope=SimpleNamespace(
                enclosing_step=SimpleNamespace(
                    step_name="Review",
                    step_id="root.review",
                    visit_count=1,
                ),
                loop_iteration=None,
            )
        ),
        evidence=SimpleNamespace(evidence_sha256="sha256:" + "a" * 64),
        frozen=SimpleNamespace(frozen_sha256="sha256:" + "b" * 64),
    )

    monkeypatch.setattr(
        manager,
        "_write_state",
        lambda: (_ for _ in ()).throw(OSError("injected state write failure")),
    )

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.atomic_success_commit(prepared, deadline=10**18)

    assert raised.value.diagnostic.reason == "workflow_state_commit_failed"
    assert manager.state_file.read_bytes() == disk_before
    assert manager.state is not None
    assert manager.state.to_dict() == live_before
    assert binding.state == live_before
    assert not hasattr(executor, "_phased_authoritative_result_ids")


def _q2_validation_binding(tmp_path):
    executor = _executor()
    executor.workspace = tmp_path
    executor._resolve_workspace_path = MethodType(
        lambda self, path: self.workspace / path,
        executor,
    )
    expected_outputs = [
        {
            "name": "report",
            "path": "artifacts/report.txt",
            "type": "string",
            "required": True,
        }
    ]
    executor._q2_expected_outputs_with_subjects = MethodType(
        lambda self, step, expected: expected,
        executor,
    )
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)
    binding.executor = executor
    binding.step = {}
    binding.resolved_expected_outputs = expected_outputs
    binding.resolved_output_bundle = {
        "path": "artifacts/result.json",
        "fields": [
            {
                "name": "approved",
                "json_pointer": "/approved",
                "type": "bool",
                "required": True,
            }
        ],
    }
    binding.preflight = CandidatePreflight.create(
        bindings=(
            CandidatePathBinding(
                contract_ordinal=0,
                role="expected_output",
                logical_name="report",
                workspace_relative_path="artifacts/report.txt",
            ),
            CandidatePathBinding(
                contract_ordinal=1,
                role="structured_bundle",
                logical_name="__structured_result_bundle__",
                workspace_relative_path="artifacts/result.json",
            ),
        )
    )
    binding._validated_artifacts = {}
    binding._validated_structured_artifacts = {}
    return binding


def test_real_missing_artifact_and_valid_bundle_keep_both_q2_diagnostics_exact(
    tmp_path,
) -> None:
    binding = _q2_validation_binding(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "result.json").write_text(
        '{"approved":true}\n',
        encoding="utf-8",
    )
    snapshot = binding.snapshot_candidates(
        binding.preflight,
        submission_ordinal=1,
    )

    output = binding.validate_output_positions(snapshot)
    structured = binding.validate_structured_result(snapshot)

    assert output.diagnostic is not None
    assert output.diagnostic.rejected_value.canonical_value == (
        "missing_output_file"
    )
    assert structured.diagnostic is None
    assert structured.result is not None


def test_real_valid_artifact_and_malformed_bundle_keep_both_q2_diagnostics_exact(
    tmp_path,
) -> None:
    binding = _q2_validation_binding(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "report.txt").write_text("valid\n", encoding="utf-8")
    (artifacts / "result.json").write_text("{malformed", encoding="utf-8")
    snapshot = binding.snapshot_candidates(
        binding.preflight,
        submission_ordinal=1,
    )

    output = binding.validate_output_positions(snapshot)
    structured = binding.validate_structured_result(snapshot)

    assert output.diagnostic is None
    assert output.artifacts
    assert structured.diagnostic is not None
    assert structured.diagnostic.rejected_value.canonical_value == (
        "invalid_json_document"
    )
    assert structured.result is None


def _assert_exact_operation_failure(
    raised: pytest.ExceptionInfo[PhasedOperationFailure],
    reason: str,
) -> None:
    expected = _runtime_diagnostic(reason)
    assert diagnostic_to_dict(raised.value.diagnostic) == (
        diagnostic_to_dict(expected)
    )
    assert str(raised.value) == expected.code
    assert raised.value.__cause__ is not None


@pytest.mark.parametrize(
    ("boundary", "failure_type"),
    (
        ("contract", ValueError),
        ("fragment", OSError),
        ("fragment", RuntimeError),
    ),
)
def test_compose_attempt_closes_expected_preparation_failure(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    failure_type: type[Exception],
) -> None:
    binding = object.__new__(_WorkflowPhasedProviderAttemptBindings)

    def fail_contract_resolution() -> None:
        raise failure_type("private preparation detail")

    def fail_fragment_render(allocation: object) -> None:
        del allocation
        raise failure_type("private preparation detail")

    monkeypatch.setattr(
        binding,
        "_resolve_contract_paths",
        (
            fail_contract_resolution
            if boundary == "contract"
            else lambda: None
        ),
    )
    monkeypatch.setattr(
        binding,
        "_render_fragment_and_cut",
        fail_fragment_render,
    )

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.compose_attempt(SimpleNamespace(), deadline=1000.0)

    _assert_exact_operation_failure(raised, "preparation_failed")
    assert "private preparation detail" not in str(raised.value)


def _write_complete_candidate_set(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "report.txt").write_text("valid\n", encoding="utf-8")
    (artifacts / "result.json").write_text(
        '{"approved":true}\n',
        encoding="utf-8",
    )


@pytest.mark.parametrize("operation", ("stat", "read"))
def test_snapshot_candidates_closes_candidate_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    binding = _q2_validation_binding(tmp_path)
    _write_complete_candidate_set(tmp_path)
    original_read_bytes = Path.read_bytes
    original_is_symlink = Path.is_symlink

    def fail_report_read(path: Path) -> bytes:
        if operation == "read" and path.name == "report.txt":
            raise OSError("private snapshot detail")
        return original_read_bytes(path)

    def fail_report_stat(path: Path) -> bool:
        if operation == "stat" and path.name == "report.txt":
            raise OSError("private snapshot detail")
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "read_bytes", fail_report_read)
    monkeypatch.setattr(Path, "is_symlink", fail_report_stat)

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.snapshot_candidates(binding.preflight, submission_ordinal=1)

    _assert_exact_operation_failure(raised, "candidate_freeze_failed")
    assert "private snapshot detail" not in str(raised.value)


def test_reset_candidates_closes_candidate_unlink_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _q2_validation_binding(tmp_path)
    _write_complete_candidate_set(tmp_path)
    snapshot = binding.snapshot_candidates(
        binding.preflight,
        submission_ordinal=1,
    )
    original_unlink = Path.unlink

    def fail_report_unlink(
        path: Path,
        missing_ok: bool = False,
    ) -> None:
        if path.name == "report.txt":
            raise OSError("private reset detail")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_report_unlink)

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.reset_candidates(snapshot)

    _assert_exact_operation_failure(raised, "candidate_reset_failed")
    assert "private reset detail" not in str(raised.value)


def test_freeze_candidate_closes_candidate_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _q2_validation_binding(tmp_path)
    _write_complete_candidate_set(tmp_path)
    snapshot = binding.snapshot_candidates(
        binding.preflight,
        submission_ordinal=1,
    )
    original_read_bytes = Path.read_bytes

    def fail_report_read(path: Path) -> bytes:
        if path.name == "report.txt":
            raise OSError("private freeze detail")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_report_read)

    with pytest.raises(PhasedOperationFailure) as raised:
        binding.freeze_candidate(
            snapshot,
            SimpleNamespace(),
            SimpleNamespace(),
        )

    _assert_exact_operation_failure(raised, "candidate_freeze_failed")
    assert "private freeze detail" not in str(raised.value)
