"""Public deterministic acceptance for target-2.23 phased contract delivery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import (
    dataclass,
    field,
    fields as dataclass_fields,
    is_dataclass,
    replace,
)
from enum import Enum
import hashlib
import json
import logging
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import time
from typing import Any
from unittest.mock import patch

import pytest

import orchestrator.providers.interactive_terminal as interactive_terminal_module
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalStartOutcome,
    NaturalShutdownProof,
    NoBackendAllocationProof,
    OfferReceipt,
    PaneProcessStatus,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    LoadedWorkflowBundle,
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.prompt_context_report import project_prompt_context_v2
from orchestrator.workflow.prompt_attempt_result_binding import (
    validate_prompt_attempt_result_binding,
)
from orchestrator.workflow.prompt_dependency_evidence import (
    canonical_record_bytes,
    evidence_relative_path,
)
from orchestrator.workflow.provider_phased_delivery.ledger import (
    validate_ledger_bytes,
)
from orchestrator.workflow.provider_phased_delivery.protocol import (
    SubmitRequest,
    decode_submit_binding,
    send_submit_request,
)
from orchestrator.workflow.provider_phased_delivery.runtime_bindings import (
    _WorkflowPhasedProviderAttemptBindings,
)
from orchestrator.workflow.provider_attempts import (
    ProviderAttemptScope,
    resolve_aggregate_run_owner,
    validate_provider_attempt_allocations,
    validate_provider_attempt_scope,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp import lexical_checkpoints
from orchestrator.workflow.persisted_surface import (
    serialize_persisted_workflow_surface_graph,
)
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SOURCE = (
    REPO_ROOT
    / "tests/fixtures/workflow_lisp/phased_contract_delivery/public_e2e.orc"
)
COMPATIBILITY_GOLDEN = (
    REPO_ROOT
    / "tests/fixtures/workflow_lisp/phased_contract_delivery"
    / "ordinary_compatibility.golden"
)
COMPATIBILITY_GOLDEN_DIGESTS = COMPATIBILITY_GOLDEN.with_suffix(
    ".sha256"
)
MODEL = "phased-public-model"
EFFORT = "high"
EMPTY_SHA256 = "sha256:" + hashlib.sha256(b"").hexdigest()


def _read_compatibility_golden_bytes() -> dict[tuple[str, str], bytes]:
    expected: dict[tuple[str, str], bytes] = {}
    for line in COMPATIBILITY_GOLDEN.read_bytes().splitlines(
        keepends=True
    ):
        case, boundary, payload = line.split(b"\t", 2)
        expected[(case.decode("ascii"), boundary.decode("ascii"))] = (
            payload
        )
    return expected


def _read_compatibility_golden_digests(
) -> dict[tuple[str, str], str]:
    expected: dict[tuple[str, str], str] = {}
    for line in COMPATIBILITY_GOLDEN_DIGESTS.read_text(
        encoding="ascii"
    ).splitlines():
        digest, identity = line.split("  ", 1)
        case, boundary = identity.split("/", 1)
        expected[(case, boundary)] = "sha256:" + digest
    return expected


EXPECTED_COMPATIBILITY_GOLDEN_BYTES = _read_compatibility_golden_bytes()
EXPECTED_COMPATIBILITY_SHA256 = (
    _read_compatibility_golden_digests()
)
COMPATIBILITY_CASES = (
    "2.20-omitted",
    "2.21-omitted",
    "2.22-omitted",
    "2.23-omitted",
    "2.23-composed",
)
COMPATIBILITY_BOUNDARIES = (
    "checkpoint_identity",
    "compiler_carriers_ir",
    "completed_boundary_state",
    "identity_evidence",
    "persisted_graph",
    "prepared_policy_invocation",
    "result",
)


class _SimulatedProcessCrash(BaseException):
    pass


class _PostProviderCommitCrash(BaseException):
    pass


def _compile_public(workspace: Path):
    result = compile_stage3_module(
        PUBLIC_SOURCE,
        entry_workflow="phased-review",
        provider_externs={"providers.review": "codex"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=workspace,
        lowering_route="wcc_m4",
    )
    return result.validated_bundles["phased-review"]


def _manager(
    workspace: Path,
    *,
    bundle: LoadedWorkflowBundle,
    run_id: str,
) -> StateManager:
    workspace_token = hashlib.sha256(
        str(workspace.resolve()).encode("utf-8")
    ).hexdigest()[:12]
    run_id = f"{run_id}-{workspace_token}"
    contracts = {
        name: dict(contract)
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        {
            "subject": "PUBLIC_PHASED_SUBJECT",
            "report": "artifacts/review.md",
            "model": MODEL,
            "effort": EFFORT,
        },
        workspace,
    )
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        PUBLIC_SOURCE.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return manager


def _state(manager: StateManager) -> dict[str, Any]:
    return manager._read_state_from_disk().to_dict()


def _write_candidates(
    workspace: Path,
    *,
    output_path: Path,
    mode: str,
    submission_ordinal: int,
) -> None:
    report = workspace / "artifacts/review.md"
    if submission_ordinal == 2 or mode == "invalid_structured":
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            f"VALID_REPORT_{submission_ordinal}\n",
            encoding="utf-8",
        )
    output = output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    if submission_ordinal == 1 and mode == "invalid_structured":
        output.write_bytes(b"{malformed")
    else:
        output.write_text(
            json.dumps(
                {"approved": True},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )


@dataclass
class _ControlledPhasedHarness:
    workspace: Path
    first_mode: str
    invocations: list[InteractiveMemberInvocation] = field(
        default_factory=list
    )
    offered_messages: list[bytes] = field(default_factory=list)
    receipts: list[Any] = field(default_factory=list)
    state_after_rejection: dict[str, object] | None = None
    socket_paths: list[Path] = field(default_factory=list)
    output_paths: list[Path] = field(default_factory=list)
    client_error: BaseException | None = None
    client_done: Event = field(default_factory=Event)
    adapter: "_ControlledPhasedAdapter | None" = None
    endpoint: Any = None

    def create_adapter(self) -> "_ControlledPhasedAdapter":
        if self.adapter is not None:
            raise AssertionError("one phased attempt must create one adapter")
        self.adapter = _ControlledPhasedAdapter(self)
        return self.adapter


class _ControlledPhasedAdapter:
    def __init__(self, harness: _ControlledPhasedHarness) -> None:
        self.harness = harness
        self.handle: InteractiveMemberHandle | None = None
        self.offers: Queue[bytes | None] = Queue()
        self.stop_requested = Event()
        self.thread: Thread | None = None
        self.aborted = False
        self.joined = False

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome:
        assert deadline > time.monotonic()
        assert invocation.prepared_provider_policy is not None
        assert invocation.prepared_provider_policy.model == MODEL
        assert invocation.prepared_provider_policy.effort == EFFORT
        assert set(invocation.prepared_provider_policy.to_dict()) == {
            "provider_name",
            "model",
            "effort",
            "timeout_sec",
            "input_mode",
        }
        assert all(
            token not in {"delivery", "phased", "materialization_attempts"}
            for token in invocation.resolved_command
        )
        assert invocation.pre_prompt_command is not None
        assert sum(
            token.count("${PROMPT}")
            for token in invocation.pre_prompt_command
        ) == 1
        assert any(MODEL in token for token in invocation.pre_prompt_command)
        assert all(
            "delivery" not in token
            and "materialization_attempts" not in token
            for token in invocation.pre_prompt_command
        )
        self.harness.invocations.append(invocation)
        binding = decode_submit_binding(invocation.env)
        self.harness.socket_paths.append(binding.socket_path)
        self.handle = InteractiveMemberHandle(
            adapter_instance_id="controlled-phased-adapter",
            handle_id="controlled-phased-handle",
            invocation_id=invocation.invocation_id,
            member_id=invocation.member_id,
            attempt_scope_key=invocation.attempt_scope_key,
            attempt_ordinal=invocation.attempt_ordinal,
            target="controlled:phased",
            socket_path=Path("/tmp/controlled-phased-provider.sock"),
        )
        self.thread = Thread(
            target=self._run_client,
            args=(invocation,),
            name="controlled-public-phased-client",
            daemon=True,
        )
        self.thread.start()
        return InteractiveTerminalStartOutcome(
            status="started",
            handle=self.handle,
        )

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        assert handle == self.handle
        assert deadline > time.monotonic()
        payload = literal_message.encode("utf-8")
        self.harness.offered_messages.append(payload)
        self.offers.put(payload)
        return OfferReceipt(
            status="offered",
            handle_id=handle.handle_id,
            byte_count=len(payload),
            content_sha256=(
                "sha256:" + hashlib.sha256(payload).hexdigest()
            ),
        )

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt:
        assert handle == self.handle
        assert deadline > time.monotonic()
        return CloseOfferReceipt(
            status="close_offered",
            handle_id=handle.handle_id,
        )

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof:
        assert handle == self.handle
        thread = self.thread
        assert thread is not None
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
        self.joined = not thread.is_alive()
        return NaturalShutdownProof(
            disposition="natural_exit",
            handle_id=handle.handle_id,
            return_code=0,
            pane_absent=self.joined,
            server_absent=self.joined,
            proof_complete=self.joined,
        )

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof:
        assert handle == self.handle
        self.aborted = True
        self.stop_requested.set()
        self.offers.put(None)
        thread = self.thread
        if thread is not None:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        complete = thread is None or not thread.is_alive()
        return FailedCleanupProof(
            disposition="failed_cleanup",
            handle_id=handle.handle_id,
            pane_absent=complete,
            server_absent=complete,
            cleanup_complete=complete,
            error_code=None if complete else "controlled_client_alive",
        )

    def probe_process_status(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> PaneProcessStatus:
        assert handle == self.handle
        assert deadline > time.monotonic()
        return PaneProcessStatus(state="running", return_code=None)

    def prove_no_backend_allocation(self) -> NoBackendAllocationProof:
        return NoBackendAllocationProof(
            disposition="no_backend_allocation",
            backend_resource_allocated=False,
            proof_complete=True,
        )

    def _run_client(self, invocation: InteractiveMemberInvocation) -> None:
        try:
            binding = decode_submit_binding(invocation.env)
            output_path = Path(
                invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
            )
            if not output_path.is_absolute():
                output_path = self.harness.workspace / output_path
            self.harness.output_paths.append(output_path)
            for ordinal in (1, 2):
                try:
                    offered = self.offers.get(timeout=5)
                except Empty as exc:
                    raise AssertionError(
                        "materialization turn was not offered"
                    ) from exc
                if offered is None or self.stop_requested.is_set():
                    return
                _write_candidates(
                    self.harness.workspace,
                    output_path=output_path,
                    mode=self.harness.first_mode,
                    submission_ordinal=ordinal,
                )
                receipt = send_submit_request(
                    SubmitRequest(
                        attempt_scope_sha256=(
                            binding.attempt_scope_sha256
                        ),
                        endpoint_instance_id=(
                            binding.endpoint_instance_id
                        ),
                        binding_token=binding.binding_token,
                        client_request_id=f"public-request-{ordinal}",
                        payload_sha256=EMPTY_SHA256,
                    ),
                    binding=binding,
                )
                self.harness.receipts.append(receipt)
                if receipt.status == "retry_queued":
                    state_path = next(
                        (
                            self.harness.workspace
                            / ".orchestrate/runs"
                        ).glob("*/state.json")
                    )
                    self.harness.state_after_rejection = json.loads(
                        state_path.read_text(encoding="utf-8")
                    )
                    assert not (
                        self.harness.workspace / "artifacts/review.md"
                    ).exists()
                    assert not output_path.exists()
                    continue
                assert receipt.status == "accepted_closing"
                return
        except BaseException as exc:
            self.harness.client_error = exc
        finally:
            self.harness.client_done.set()


def _install_harness(
    monkeypatch: pytest.MonkeyPatch,
    harness: _ControlledPhasedHarness,
) -> None:
    monkeypatch.setattr(
        interactive_terminal_module,
        "InteractiveTerminalTurnQueueAdapter",
        lambda *_args, **_kwargs: harness.create_adapter(),
    )
    original_create_endpoint = (
        _WorkflowPhasedProviderAttemptBindings.create_endpoint
    )

    def create_endpoint(
        self: _WorkflowPhasedProviderAttemptBindings,
        composition: object,
    ) -> object:
        endpoint = original_create_endpoint(self, composition)
        harness.endpoint = endpoint
        return endpoint

    monkeypatch.setattr(
        _WorkflowPhasedProviderAttemptBindings,
        "create_endpoint",
        create_endpoint,
    )


def _execute(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    first_mode: str,
    run_id: str,
    interrupt_after_provider_commit: bool = False,
) -> tuple[
    LoadedWorkflowBundle,
    StateManager,
    _ControlledPhasedHarness,
    dict[str, Any],
]:
    bundle = _compile_public(workspace)
    manager = _manager(workspace, bundle=bundle, run_id=run_id)
    harness = _ControlledPhasedHarness(
        workspace=workspace,
        first_mode=first_mode,
    )
    _install_harness(monkeypatch, harness)
    validator_calls: list[tuple[str, int]] = []
    original_output = (
        _WorkflowPhasedProviderAttemptBindings.validate_output_positions
    )
    original_structured = (
        _WorkflowPhasedProviderAttemptBindings.validate_structured_result
    )

    def validate_output(self, snapshot):
        validator_calls.append(("output", snapshot.submission_ordinal))
        return original_output(self, snapshot)

    def validate_structured(self, snapshot):
        validator_calls.append(("structured", snapshot.submission_ordinal))
        return original_structured(self, snapshot)

    monkeypatch.setattr(
        _WorkflowPhasedProviderAttemptBindings,
        "validate_output_positions",
        validate_output,
    )
    monkeypatch.setattr(
        _WorkflowPhasedProviderAttemptBindings,
        "validate_structured_result",
        validate_structured,
    )
    executor = WorkflowExecutor(
        bundle,
        workspace,
        manager,
        retry_delay_ms=0,
    )
    if interrupt_after_provider_commit:
        original_finalize = StateManager.finalize_step_with_dataflow

        def interrupt_after_atomic_commit(
            self,
            *args: Any,
            **kwargs: Any,
        ):
            original_finalize(self, *args, **kwargs)
            raise _PostProviderCommitCrash

        with patch.object(
            StateManager,
            "finalize_step_with_dataflow",
            interrupt_after_atomic_commit,
        ), pytest.raises(_PostProviderCommitCrash):
            executor.execute(on_error="stop")
        completed = _state(manager)
    else:
        completed = executor.execute(on_error="stop")
    assert validator_calls == [
        ("output", 1),
        ("structured", 1),
        ("output", 2),
        ("structured", 2),
    ], {
        "error": completed.get("error"),
        "steps": completed.get("steps"),
    }
    return bundle, manager, harness, completed


def _ledger_rows(manager: StateManager) -> list[dict[str, Any]]:
    paths = list(
        manager.run_root.rglob(
            "attempt-*-provider-prompt-phases.jsonl"
        )
    )
    assert len(paths) == 1
    assert validate_ledger_bytes(paths[0].read_bytes()) == {
        "schema_version": (
            "provider_prompt_phase_ledger_validation.v1"
        ),
        "status": "complete",
        "reason": "complete",
        "row_count": len(paths[0].read_text(encoding="ascii").splitlines()),
        "last_contiguous_seq": (
            len(paths[0].read_text(encoding="ascii").splitlines()) - 1
        ),
        "terminal_event": "publication_succeeded",
    }
    return [
        json.loads(line)
        for line in paths[0].read_text(encoding="ascii").splitlines()
    ]


def _published_evidence(
    manager: StateManager,
    state: dict[str, Any],
) -> dict[str, Any]:
    allocations = validate_provider_attempt_allocations(
        state["provider_attempt_allocations"]
    )
    [allocation] = allocations.values()
    scope = ProviderAttemptScope.from_dict(allocation["scope"])
    validate_provider_attempt_scope(
        scope,
        resolve_aggregate_run_owner(manager),
    )
    last_ordinal = allocation["last_allocated_ordinal"]
    step = state["steps"][scope.enclosing_step.step_name]
    debug = step.get("debug", {})
    assert isinstance(debug, Mapping)
    phased = debug.get("phased_delivery")
    binding = debug.get("prompt_attempt_result_binding")
    if phased is not None:
        assert isinstance(phased, Mapping)
        relative_path = phased["functional_evidence"]
        assert isinstance(relative_path, str)
        matching_ordinals = [
            ordinal
            for ordinal in range(1, last_ordinal + 1)
            if str(evidence_relative_path(scope, ordinal))
            == relative_path
        ]
        [ordinal] = matching_ordinals
        validated_binding = None
    elif binding is not None:
        validated_binding = validate_prompt_attempt_result_binding(
            binding
        )
        assert validated_binding["scope_sha256"] == scope.key
        ordinal = validated_binding["attempt_ordinal"]
        relative_path = validated_binding["evidence_relative_path"]
    else:
        validated_binding = None
        ordinal = last_ordinal
        relative_path = str(evidence_relative_path(scope, ordinal))
    assert 1 <= ordinal <= last_ordinal
    assert relative_path == str(evidence_relative_path(scope, ordinal))
    payload = (manager.run_root / relative_path).read_bytes()
    evidence = json.loads(payload)
    assert isinstance(evidence, dict)
    canonical = canonical_record_bytes(
        evidence,
        compiler_fragment_identity_schema_version=allocation.get(
            "prompt_fragment_identity_schema_version"
        ),
    )
    assert canonical == payload
    assert evidence["attempt"]["scope"] == scope.to_dict()
    assert evidence["attempt"]["scope_sha256"] == scope.key
    assert evidence["attempt"]["ordinal"] == ordinal
    if validated_binding is not None:
        assert validated_binding["evidence_file_sha256"] == (
            "sha256:" + hashlib.sha256(payload).hexdigest()
        )
    return evidence


@pytest.mark.parametrize(
    "first_mode",
    ("invalid_artifact", "invalid_structured"),
)
def test_public_phased_retry_is_atomic_and_projects_exact_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_mode: str,
) -> None:
    with patch(
        "orchestrator.workflow.executor."
        "attach_prompt_attempt_result_binding",
        side_effect=AssertionError(
            "phased identity-v2 route attempted Q4 result binding"
        ),
    ):
        _, manager, harness, completed = _execute(
            tmp_path,
            monkeypatch,
            first_mode=first_mode,
            run_id=f"public-{first_mode}",
        )

    assert completed["status"] == "completed"
    assert completed["workflow_outputs"] == {"return__approved": True}
    [step] = completed["steps"].values()
    assert step["status"] == "completed"
    assert "prompt_attempt_result_binding" not in step.get(
        "debug",
        {},
    )
    assert step["artifacts"]["approved"] is True
    assert step["artifacts"]["report"] == "VALID_REPORT_2\n"
    assert len(harness.invocations) == 1
    assert len(harness.offered_messages) == 2
    assert [receipt.status for receipt in harness.receipts] == [
        "retry_queued",
        "accepted_closing",
    ]
    assert harness.client_error is None
    assert harness.client_done.wait(1)
    assert harness.adapter is not None
    assert harness.adapter.joined is True
    assert harness.adapter.aborted is False
    assert harness.adapter.thread is not None
    assert not harness.adapter.thread.is_alive()
    assert harness.state_after_rejection is not None
    assert harness.state_after_rejection.get("workflow_outputs", {}) == {}
    assert harness.state_after_rejection.get("artifact_versions", {}) == {}
    assert harness.state_after_rejection.get("steps", {}) == {}
    assert len(harness.output_paths) == 1

    rows = _ledger_rows(manager)
    header = rows[0]
    events = [row for row in rows[1:] if row["record_kind"] == "event"]
    assert sum(row["event"] == "task_started" for row in events) == 1
    assert sum(
        row["event"] == "publication_succeeded" for row in events
    ) == 1
    rejected = next(
        row for row in events if row["event"] == "validation_rejected"
    )
    frozen = next(
        row for row in events if row["event"] == "candidate_frozen"
    )
    assert rejected["payload"]["submission_ordinal"] == 1
    assert frozen["payload"]["submission_ordinal"] == 2
    assert rejected["payload"]["candidate_manifest"]["disposition"] == (
        "rejected"
    )
    assert frozen["payload"]["candidate_manifest"]["disposition"] == "frozen"
    assert tuple(
        row["contract_ordinal"]
        for row in frozen["payload"]["candidate_manifest"]["rows"]
    ) == (0, 1)
    [rejection_diagnostic] = rejected["payload"]["diagnostics"]
    assert rejection_diagnostic["reason"] == (
        "output_validation_failed"
        if first_mode == "invalid_artifact"
        else "structured_result_validation_failed"
    )
    rejected_rows = rejected["payload"]["candidate_manifest"]["rows"]
    assert [row["presence"] for row in rejected_rows] == (
        ["missing", "regular"]
        if first_mode == "invalid_artifact"
        else ["regular", "regular"]
    )
    offered_turns = [
        row["payload"]["turn"]
        for row in events
        if row["event"] == "turn_offered"
    ]
    assert [turn["phase"] for turn in offered_turns] == [
        "initial_materialization",
        "retry_materialization",
    ]
    assert (
        offered_turns[0]["canonical_slice"]
        == offered_turns[1]["canonical_slice"]
        == header["materialization_slice"]
    )
    ingress = next(
        row for row in events if row["event"] == "ingress_shutdown_finished"
    )
    assert ingress["payload"]["endpoint_zero_survivor_proven"] is True
    assert all(not path.exists() for path in harness.socket_paths)

    state = _state(manager)
    evidence = _published_evidence(manager, state)
    assert evidence["schema"] == (
        "workflow_prompt_fragment_snapshot.functional.v3"
    )
    identity = evidence["prompt_attempt_identity"]
    assert identity["schema_version"] == "workflow_prompt_attempt_identity.v2"
    assert [row["phase"] for row in identity["actual_deliveries"]] == [
        "task",
        "initial_materialization",
        "retry_materialization",
    ]
    assert "final_prompt" not in identity
    assert all(
        delivery["delivered_turn"]["sha256"]
        != identity["canonical_composed"]["sha256"]
        for delivery in identity["actual_deliveries"]
    )
    assert identity["canonical_composed"] == header["canonical_composed"]
    report = project_prompt_context_v2(state, manager.run_root)
    assert report["schema_version"] == "workflow_prompt_context_report.v2"
    [attempt] = report["attempts"]
    assert attempt["record_status"] == "snapshot"
    assert attempt["identity"]["identity_version"] == (
        "workflow_prompt_attempt_identity.v2"
    )
    assert attempt["identity"]["legacy_final_prompt_sha256"] is None
    assert attempt["identity"]["actual_deliveries"] == (
        identity["actual_deliveries"]
    )
    ledger_bytes = next(
        manager.run_root.rglob(
            "attempt-*-provider-prompt-phases.jsonl"
        )
    ).read_bytes()
    for forbidden in (
        b"PUBLIC_PHASED_SUBJECT",
        b"VALID_REPORT",
        MODEL.encode("utf-8"),
        b'{"approved":true}',
    ):
        assert forbidden not in ledger_bytes


def _clean_after_simulated_crash(
    harness: _ControlledPhasedHarness,
) -> None:
    adapter = harness.adapter
    if adapter is not None:
        adapter.stop_requested.set()
        adapter.offers.put(None)
    endpoint = harness.endpoint
    if endpoint is not None:
        endpoint.stop_admission()
        endpoint.shutdown(deadline=time.monotonic() + 2)
    if adapter is not None and adapter.handle is not None:
        adapter.abort(adapter.handle, time.monotonic() + 2)


@pytest.mark.parametrize(
    ("boundary", "first_mode"),
    (
        ("BEFORE_INITIAL_OFFER", "invalid_artifact"),
        ("BEFORE_RETRY_OFFER", "invalid_structured"),
        ("VALID_FROZEN", "invalid_artifact"),
    ),
)
def test_public_phased_crash_resume_reruns_whole_visit_from_task_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    boundary: str,
    first_mode: str,
) -> None:
    bundle = _compile_public(tmp_path)
    manager = _manager(
        tmp_path,
        bundle=bundle,
        run_id=f"crash-{boundary.lower()}",
    )
    harness = _ControlledPhasedHarness(tmp_path, first_mode)
    original_adapter_factory = (
        interactive_terminal_module.InteractiveTerminalTurnQueueAdapter
    )
    original_create_endpoint = (
        _WorkflowPhasedProviderAttemptBindings.create_endpoint
    )
    _install_harness(monkeypatch, harness)
    original_receive = (
        _WorkflowPhasedProviderAttemptBindings.receive_attempt_event
    )
    crashed = False

    def receive(self, *, boundary: str, endpoint, deadline: float):
        nonlocal crashed
        if not crashed and boundary == boundary_under_test:
            crashed = True
            raise _SimulatedProcessCrash
        return original_receive(
            self,
            boundary=boundary,
            endpoint=endpoint,
            deadline=deadline,
        )

    boundary_under_test = boundary
    monkeypatch.setattr(
        _WorkflowPhasedProviderAttemptBindings,
        "receive_attempt_event",
        receive,
    )
    with pytest.raises(_SimulatedProcessCrash):
        WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    assert crashed is True
    interrupted = _state(manager)
    assert interrupted["status"] == "running"
    assert interrupted["current_step"]["status"] == "running"
    assert interrupted["current_step"]["visit_count"] == 1
    _clean_after_simulated_crash(harness)
    assert all(not path.exists() for path in harness.socket_paths)
    if harness.adapter is not None and harness.adapter.thread is not None:
        assert not harness.adapter.thread.is_alive()
    [interrupted_ledger] = list(
        manager.run_root.rglob(
            "attempt-*-provider-prompt-phases.jsonl"
        )
    )
    interrupted_attempt_root = interrupted_ledger.parent
    interrupted_attempt_bytes = {
        path.relative_to(interrupted_attempt_root).as_posix():
        path.read_bytes()
        for path in interrupted_attempt_root.rglob("*")
        if path.is_file()
    }
    [interrupted_invocation] = harness.invocations

    monkeypatch.setattr(
        interactive_terminal_module,
        "InteractiveTerminalTurnQueueAdapter",
        original_adapter_factory,
    )
    monkeypatch.setattr(
        _WorkflowPhasedProviderAttemptBindings,
        "create_endpoint",
        original_create_endpoint,
    )
    monkeypatch.setattr(
        _WorkflowPhasedProviderAttemptBindings,
        "receive_attempt_event",
        original_receive,
    )
    resumed_harness = _ControlledPhasedHarness(
        tmp_path,
        first_mode,
    )
    _install_harness(monkeypatch, resumed_harness)
    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()

    with caplog.at_level(logging.WARNING):
        resumed = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
        ).execute(on_error="stop", resume=True)

    assert resumed["status"] == "completed"
    assert resumed.get("current_step") is None
    [step] = resumed["steps"].values()
    assert step["status"] == "completed"
    assert step["visit_count"] == 2
    assert step["artifacts"]["approved"] is True
    assert step["artifacts"]["report"] == "VALID_REPORT_2\n"
    [resumed_invocation] = resumed_harness.invocations
    assert resumed_invocation.invocation_id != (
        interrupted_invocation.invocation_id
    )
    assert resumed_invocation.attempt_scope_key != (
        interrupted_invocation.attempt_scope_key
    )
    assert resumed_invocation.attempt_ordinal == 1
    assert resumed_harness.adapter is not None
    assert resumed_harness.adapter.joined is True
    assert resumed_harness.adapter.aborted is False
    assert [receipt.status for receipt in resumed_harness.receipts] == [
        "retry_queued",
        "accepted_closing",
    ]

    ledgers = list(
        manager.run_root.rglob(
            "attempt-*-provider-prompt-phases.jsonl"
        )
    )
    assert len(ledgers) == 2
    [fresh_ledger] = [
        path for path in ledgers if path != interrupted_ledger
    ]
    assert validate_ledger_bytes(fresh_ledger.read_bytes())["status"] == (
        "complete"
    )
    fresh_rows = [
        json.loads(line)
        for line in fresh_ledger.read_text(
            encoding="ascii"
        ).splitlines()
    ]
    fresh_events = [
        row for row in fresh_rows if row["record_kind"] == "event"
    ]
    assert [row["event"] for row in fresh_events[:2]] == [
        "task_start_requested",
        "task_started",
    ]
    assert fresh_events[1]["payload"]["turn"]["phase"] == "task"
    assert {
        path.relative_to(interrupted_attempt_root).as_posix():
        path.read_bytes()
        for path in interrupted_attempt_root.rglob("*")
        if path.is_file()
    } == interrupted_attempt_bytes
    rerun_records = [
        record
        for record in caplog.records
        if getattr(record, "orchestrator_diagnostic", None)
        == "provider_attempt_interrupted_rerun"
    ]
    assert len(rerun_records) == 1
    assert rerun_records[0].provider_family == "phased"
    assert rerun_records[0].discarded_visit == 1
    assert rerun_records[0].next_visit == 2


def test_completed_phased_reuse_opens_no_provider_endpoint_or_phase_ledger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle, manager, _, completed = _execute(
        tmp_path,
        monkeypatch,
        first_mode="invalid_artifact",
        run_id="completed-reuse",
        interrupt_after_provider_commit=True,
    )
    completed_step = next(iter(completed["steps"].values()))
    assert completed_step["status"] == "completed"
    assert completed_step["artifacts"]["approved"] is True
    original_open = Path.open

    def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.name.endswith("-provider-prompt-phases.jsonl"):
            raise AssertionError("completed reuse opened phased ledger")
        return original_open(path, *args, **kwargs)

    resume_manager = StateManager(tmp_path, run_id=manager.run_id)
    resume_manager.load()
    with patch.object(
        Path,
        "open",
        guarded_open,
    ), patch.object(
        WorkflowExecutor,
        "_build_phased_provider_attempt_bindings",
        side_effect=AssertionError("completed reuse constructed endpoint"),
    ):
        reused = WorkflowExecutor(
            bundle,
            tmp_path,
            resume_manager,
            retry_delay_ms=0,
        ).execute(on_error="stop", resume=True)
    assert reused["status"] == "completed"
    assert reused["workflow_outputs"] == {"return__approved": True}


def _ordinary_source(target: str, *, explicit_composed: bool) -> str:
    delivery = "\n      :delivery :composed" if explicit_composed else ""
    return f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule ordinary_delivery)
  (export review)
  (defrecord Result (approved Bool))
  (defprompt review-prompt
    (:fills (subject :text))
    -> Result
    "Review {{subject}}")
  (defworkflow review
    ((subject String) (model String) (effort String))
    -> Result
    (let* ((reviewed
             (provider-result providers.review
               :prompt (review-prompt :subject subject)
               :model model
               :effort effort{delivery})))
      (record Result :approved reviewed.approved))))
"""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        + b"\n"
    )


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _plain_boundary_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _plain_boundary_value(getattr(value, item.name))
            for item in dataclass_fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _plain_boundary_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_plain_boundary_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        plain_items = [_plain_boundary_value(item) for item in value]
        return sorted(
            plain_items,
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    raise TypeError(
        f"unsupported compatibility boundary value {type(value).__name__}"
    )


_PROMPT_DERIVED_FIELD_TOKENS = {
    "compiled_prompt_fragment_identity": (
        "$PROMPT_FRAGMENT_IDENTITY_SHA256"
    ),
    "composition_sha256": "$COMPOSED_PROMPT_SHA256",
    "executable_ir_digest": "$PROMPT_DERIVED_EXECUTABLE_IR_DIGEST",
    "evidence_file_sha256": "$PROMPT_EVIDENCE_FILE_SHA256",
    "file_sha256": "$PROMPT_EVIDENCE_FILE_SHA256",
    "frontend_persisted_surface_sha256": (
        "$PROMPT_DERIVED_PERSISTED_SURFACE_SHA256"
    ),
    "normalized_contract_sha256": (
        "$PROMPT_DERIVED_COMPILER_CONTRACT_SHA256"
    ),
    "record_sha256": "$PROMPT_EVIDENCE_RECORD_SHA256",
    "semantic_ir_digest": "$PROMPT_DERIVED_SEMANTIC_IR_DIGEST",
    "source_module_digest": "$PROMPT_DERIVED_SOURCE_MODULE_DIGEST",
    "source_workflow_sha256": "$WORKFLOW_CONTENT_SHA256",
    "workflow_checksum": "$WORKFLOW_CONTENT_SHA256",
}

_OWNER_EXCLUDED_FIELD_FRAGMENTS = (
    "isolation",
    "safety",
    "sandbox",
    "secret",
    "security",
)


def _is_owner_excluded_boundary_field(field_name: str) -> bool:
    lowered = field_name.lower()
    return (
        lowered == "command"
        or lowered.endswith("_command")
        or any(
            fragment in lowered
            for fragment in _OWNER_EXCLUDED_FIELD_FRAGMENTS
        )
    )


def _prompt_hash_token(
    field_name: str,
    path: tuple[str, ...],
) -> str | None:
    if field_name in _PROMPT_DERIVED_FIELD_TOKENS:
        return _PROMPT_DERIVED_FIELD_TOKENS[field_name]
    if field_name != "sha256":
        return None
    if "final_prompt" in path:
        return "$FINAL_PROMPT_SHA256"
    if "fragment_program" in path:
        return "$PROMPT_FRAGMENT_ROLE_SHA256"
    if "runtime_contributions" in path:
        return (
            "$PROMPT_RUNTIME_CONTRIBUTION_CONTENT_SHA256"
            if "rows" in path
            else "$PROMPT_RUNTIME_CONTRIBUTIONS_ROLE_SHA256"
        )
    return None


def _prompt_hash_binding_rows(
    value: object,
    *,
    path: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = (*path, key)
            token = _prompt_hash_token(key, item_path)
            if token is not None and isinstance(item, str):
                is_well_formed = (
                    item.startswith("source:")
                    if key == "source_module_digest"
                    else _is_sha256(item)
                )
                rows.append(
                    {
                        "path": "/".join(item_path),
                        "replacement": token,
                        "algorithm": (
                            "source-content-digest"
                            if key == "source_module_digest"
                            else "sha256"
                        ),
                        "well_formed": is_well_formed,
                    }
                )
            rows.extend(
                _prompt_hash_binding_rows(item, path=item_path)
            )
    elif isinstance(value, list):
        for ordinal, item in enumerate(value):
            rows.extend(
                _prompt_hash_binding_rows(
                    item,
                    path=(*path, f"[{ordinal}]"),
                )
            )
    return rows


def _normalize_boundary_value(
    value: object,
    *,
    path: tuple[str, ...] = (),
    exact_replacements: Mapping[str, str],
) -> object:
    """Preserve included shape; omit the owner's out-of-scope surfaces.

    Owner-scope omission takes precedence. Exact runtime/workspace values
    follow, then the closed prompt-derived field table. Every remaining key
    and value survives byte-for-byte canonicalization.
    """

    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if _is_owner_excluded_boundary_field(key):
                continue
            normalized_key = exact_replacements.get(key, key)
            normalized[normalized_key] = _normalize_boundary_value(
                item,
                path=(*path, normalized_key),
                exact_replacements=exact_replacements,
            )
        return normalized
    if isinstance(value, list):
        return [
            _normalize_boundary_value(
                item,
                path=(*path, f"[{ordinal}]"),
                exact_replacements=exact_replacements,
            )
            for ordinal, item in enumerate(value)
        ]
    field_name = path[-1] if path else ""
    if field_name in {"started_at", "updated_at"}:
        return "$RUNTIME_TIMESTAMP"
    if field_name in {"prompt", "prepared_prompt", "template_utf8"}:
        return "$PROMPT_PROSE"
    if field_name == "bytes" and (
        "final_prompt" in path or "runtime_contributions" in path
    ):
        return "$PROMPT_UTF8_BYTE_COUNT"
    prompt_hash_token = _prompt_hash_token(field_name, path)
    if prompt_hash_token is not None:
        return prompt_hash_token
    if isinstance(value, str):
        if value in exact_replacements:
            return exact_replacements[value]
        normalized_text = value
        for raw, replacement in sorted(
            exact_replacements.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if raw:
                normalized_text = normalized_text.replace(raw, replacement)
        return normalized_text
    return value


def _compiler_carrier_projection(
    bundle: LoadedWorkflowBundle,
) -> dict[str, object]:
    surface_step = bundle.surface.steps[0]
    executable_node = next(iter(bundle.ir.nodes.values()))
    return {
        "target": bundle.surface.version,
        "surface_step": _plain_boundary_value(surface_step),
        "executable_ir_node": _plain_boundary_value(
            executable_node
        ),
    }


def test_compiler_boundary_detects_previously_unselected_common_field(
    tmp_path: Path,
) -> None:
    source = tmp_path / "mutation.orc"
    source.write_text(
        _ordinary_source("2.23", explicit_composed=False),
        encoding="utf-8",
    )
    bundle = compile_stage3_module(
        source,
        entry_workflow="review",
        provider_externs={"providers.review": "codex"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    ).validated_bundles["review"]
    surface_step = bundle.surface.steps[0]
    tampered_step = replace(
        surface_step,
        common=replace(
            surface_step.common,
            allow_parse_error=True,
        ),
    )
    tampered = replace(
        bundle,
        surface=replace(
            bundle.surface,
            steps=(tampered_step,),
        ),
    )

    original_bytes = _canonical_bytes(
        _normalize_boundary_value(
            _compiler_carrier_projection(bundle),
            exact_replacements={},
        )
    )
    tampered_bytes = _canonical_bytes(
        _normalize_boundary_value(
            _compiler_carrier_projection(tampered),
            exact_replacements={},
        )
    )
    assert tampered_bytes != original_bytes


def _persisted_carrier_projection(
    bundle: LoadedWorkflowBundle,
) -> dict[str, object]:
    payload = serialize_persisted_workflow_surface_graph(bundle)
    projected = _plain_boundary_value(payload)
    assert isinstance(projected, dict)
    return projected


def _checkpoint_carrier_projection(
    workspace: Path,
    bundle: LoadedWorkflowBundle,
) -> dict[str, object]:
    identity = lexical_checkpoints.checkpoint_runtime_program_identity(
        state_manager=StateManager(
            workspace,
            run_id="compatibility-characterization",
        ),
        runtime_plan=bundle.runtime_plan,
        executable_ir=bundle.ir,
    )
    projected = _plain_boundary_value(identity)
    assert isinstance(projected, dict)
    return projected


def _provider_invocation_projection(invocation: object) -> dict[str, object]:
    policy = getattr(invocation, "prepared_provider_policy")
    assert policy is not None
    projected = _plain_boundary_value(
        {
            "prepared_provider_policy": policy.to_dict(),
            "invocation": invocation,
        }
    )
    assert isinstance(projected, dict)
    return projected


def _evidence_identity_projection(
    manager: StateManager,
    completed: dict[str, Any],
) -> dict[str, object]:
    evidence = _published_evidence(manager, completed)
    projected = _plain_boundary_value(evidence)
    assert isinstance(projected, dict)
    return projected


def _result_projection(
    completed: dict[str, Any],
    *,
    provider_execution_result: ProviderExecutionResult,
    output_bundle_bytes: bytes,
) -> dict[str, object]:
    [step] = completed["steps"].values()
    projected = _plain_boundary_value(
        {
            "provider_execution_result": provider_execution_result,
            "output_bundle_bytes": output_bundle_bytes,
            "provider_artifacts": step["artifacts"],
            "workflow_outputs": completed["workflow_outputs"],
        }
    )
    assert isinstance(projected, dict)
    return projected


def _completed_boundary_projection(
    completed: dict[str, Any],
) -> dict[str, object]:
    projected = _plain_boundary_value(completed)
    assert isinstance(projected, dict)
    return projected


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _boundary_exact_replacements(
    *,
    workspace: Path,
    manager: StateManager,
    invocation: object,
    evidence: dict[str, Any],
    completed: dict[str, Any],
) -> dict[str, str]:
    allocations = completed["provider_attempt_allocations"]
    assert isinstance(allocations, dict)
    [attempt_scope_sha256] = allocations
    attempt = evidence["attempt"]
    assert isinstance(attempt, dict)
    replacements = {
        workspace.resolve().as_posix(): "$WORKSPACE",
        manager.run_id: "$RUN_ID",
        attempt_scope_sha256: "$ATTEMPT_SCOPE_SHA256",
        str(attempt["visit_key"]): "$VISIT_KEY",
    }
    if attempt_scope_sha256.startswith("sha256:"):
        replacements[attempt_scope_sha256[7:31]] = (
            "$ATTEMPT_SCOPE_PREFIX"
        )
    prompt = getattr(invocation, "prompt")
    prepared_prompt = getattr(invocation, "prepared_prompt")
    if isinstance(prompt, str):
        replacements[prompt] = "$PROMPT_PROSE"
    if isinstance(prepared_prompt, str):
        replacements[prepared_prompt] = "$PROMPT_PROSE"
    return replacements


def _boundary_relationships(
    *,
    bundle: LoadedWorkflowBundle,
    invocation: object,
    evidence: dict[str, Any],
    completed: dict[str, Any],
    provider_execution_result: ProviderExecutionResult,
    output_bundle_bytes: bytes,
) -> dict[str, dict[str, object]]:
    surface_step = bundle.surface.steps[0]
    executable_config = next(
        iter(bundle.ir.nodes.values())
    ).execution_config
    fragment_contract = surface_step.compiler_prompt_fragment_contract
    fragment_identities = [
        surface_step.compiled_prompt_fragment_identity,
        getattr(
            executable_config,
            "compiled_prompt_fragment_identity",
        ),
    ]
    if fragment_contract is not None:
        fragment_identities.append(
            fragment_contract.compiled_prompt_fragment_identity
        )
    prompt = getattr(invocation, "prompt")
    prepared_prompt = getattr(invocation, "prepared_prompt")
    assert isinstance(prompt, str)
    prompt_bytes = prompt.encode("utf-8")
    final_prompt = evidence["final_prompt"]
    assert isinstance(final_prompt, dict)
    identity = evidence.get("prompt_attempt_identity")
    identity_final_prompt = (
        identity.get("final_prompt")
        if isinstance(identity, dict)
        else None
    )
    identity_roles = (
        identity.get("roles")
        if isinstance(identity, dict)
        else None
    )
    provider_policy_payload = None
    if isinstance(identity_roles, dict):
        provider_policy_role = identity_roles.get("provider_policy")
        if isinstance(provider_policy_role, dict):
            provider_policy_payload = provider_policy_role.get("payload")
    prepared_policy = getattr(
        invocation,
        "prepared_provider_policy",
    )
    assert prepared_policy is not None
    run = evidence["run"]
    assert isinstance(run, dict)
    return {
        "compiler_carriers_ir": {
            "fragment_identity_algorithm": "sha256",
            "fragment_identity_fields_equal": (
                len(set(fragment_identities)) == 1
            ),
            "fragment_identity_fields_well_formed": all(
                _is_sha256(value) for value in fragment_identities
            ),
        },
        "persisted_graph": {
            "canonical_serializer": (
                "canonical_persisted_workflow_surface_graph"
            ),
            "fragment_identity_matches_compiler": True,
        },
        "checkpoint_identity": {
            "checkpoint_schema_version": (
                "workflow_lisp_lexical_checkpoint.v1"
            ),
            "prompt_derived_program_digests_normalized": True,
        },
        "prepared_policy_invocation": {
            "prepared_prompt_equals_prompt": prepared_prompt == prompt,
            "rendered_prompt_sha256_algorithm": "sha256",
            "rendered_prompt_sha256_matches_evidence": (
                _sha256(prompt_bytes) == final_prompt["sha256"]
            ),
            "rendered_prompt_utf8_length_matches_evidence": (
                len(prompt_bytes) == final_prompt["bytes"]
            ),
            "prepared_policy_matches_identity_role": (
                None
                if provider_policy_payload is None
                else provider_policy_payload == prepared_policy.to_dict()
            ),
        },
        "identity_evidence": {
            "record_sha256_algorithm": "sha256",
            "record_sha256_well_formed": _is_sha256(
                evidence["record_sha256"]
            ),
            "final_prompt_identity_matches_record": (
                None
                if identity_final_prompt is None
                else identity_final_prompt == final_prompt
            ),
            "fragment_identity_matches_compiler": (
                evidence["compiled_prompt_fragment_identity"]
                == fragment_identities[0]
            ),
        },
        "result": {
            "output_bundle_sha256": _sha256(output_bundle_bytes),
            "provider_exit_code": provider_execution_result.exit_code,
            "typed_provider_and_workflow_results_equal": (
                next(iter(completed["steps"].values()))["artifacts"][
                    "approved"
                ]
                == completed["workflow_outputs"]["return__approved"]
            ),
        },
        "completed_boundary_state": {
            "workflow_checksum_matches_evidence": (
                completed["workflow_checksum"] == run["workflow_checksum"]
            ),
            "terminal_status": completed["status"],
        },
    }


def _compatibility_golden_bytes(
    *,
    workspace: Path,
    bundle: LoadedWorkflowBundle,
    invocation: object,
    manager: StateManager,
    completed: dict[str, Any],
    provider_execution_result: ProviderExecutionResult,
    output_bundle_bytes: bytes,
) -> dict[str, bytes]:
    evidence = _published_evidence(manager, completed)
    boundaries = {
        "compiler_carriers_ir": _compiler_carrier_projection(bundle),
        "persisted_graph": _persisted_carrier_projection(bundle),
        "checkpoint_identity": _checkpoint_carrier_projection(
            workspace,
            bundle,
        ),
        "prepared_policy_invocation": _provider_invocation_projection(
            invocation
        ),
        "identity_evidence": _evidence_identity_projection(
            manager,
            completed,
        ),
        "result": _result_projection(
            completed,
            provider_execution_result=provider_execution_result,
            output_bundle_bytes=output_bundle_bytes,
        ),
        "completed_boundary_state": _completed_boundary_projection(
            completed
        ),
    }
    replacements = _boundary_exact_replacements(
        workspace=workspace,
        manager=manager,
        invocation=invocation,
        evidence=evidence,
        completed=completed,
    )
    relationships = _boundary_relationships(
        bundle=bundle,
        invocation=invocation,
        evidence=evidence,
        completed=completed,
        provider_execution_result=provider_execution_result,
        output_bundle_bytes=output_bundle_bytes,
    )
    normalization_precedence = [
        "preserve complete included boundary shape",
        "omit owner-excluded runtime-control surfaces",
        "normalize exact workspace, run, and timestamp coordinates",
        "normalize authored or rendered prompt prose and prompt-derived hashes",
        "exclude report bytes",
        "preserve every remaining key and value",
    ]
    return {
        name: _canonical_bytes(
            {
                "schema": "ordinary_provider_boundary_golden.v2",
                "owner_excluded_surfaces": "runtime_owner_domain",
                "normalization_precedence": normalization_precedence,
                "relationships": {
                    **relationships[name],
                    "normalized_prompt_hash_bindings": (
                        _normalize_boundary_value(
                            _prompt_hash_binding_rows(payload),
                            exact_replacements=replacements,
                        )
                    ),
                },
                "payload": _normalize_boundary_value(
                    payload,
                    exact_replacements=replacements,
                ),
            }
        )
        for name, payload in boundaries.items()
    }


@pytest.mark.parametrize(
    ("target", "explicit_composed"),
    (
        ("2.20", False),
        ("2.21", False),
        ("2.22", False),
        ("2.23", False),
        ("2.23", True),
    ),
)
def test_public_ordinary_delivery_matrix_preserves_provider_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    explicit_composed: bool,
) -> None:
    case_key = f"{target}-{'composed' if explicit_composed else 'omitted'}"
    expected_identities = {
        (case, boundary)
        for case in COMPATIBILITY_CASES
        for boundary in COMPATIBILITY_BOUNDARIES
    }
    assert set(EXPECTED_COMPATIBILITY_GOLDEN_BYTES) == expected_identities
    assert set(EXPECTED_COMPATIBILITY_SHA256) == expected_identities
    source = tmp_path / "ordinary.orc"
    source.write_text(
        _ordinary_source(target, explicit_composed=explicit_composed),
        encoding="utf-8",
    )
    result = compile_stage3_module(
        source,
        entry_workflow="review",
        provider_externs={"providers.review": "codex"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    bundle = result.validated_bundles["review"]
    contracts = {
        name: dict(contract)
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    run_id = f"ordinary-{target.replace('.', '-')}-{explicit_composed}"
    manager = StateManager(tmp_path, run_id=run_id)
    manager.initialize(
        source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bind_workflow_inputs(
            contracts,
            {
                "subject": "ORDINARY_SUBJECT",
                "model": MODEL,
                "effort": EFFORT,
            },
            tmp_path,
        ),
    )
    invocations: list[object] = []
    provider_execution_results: list[ProviderExecutionResult] = []
    output_bundle_payloads: list[bytes] = []

    def execute_provider(_self, invocation, **_kwargs):
        invocations.append(invocation)
        assert invocation.prepared_provider_policy.model == MODEL
        assert invocation.prepared_provider_policy.effort == EFFORT
        assert all(
            token not in {
                "delivery",
                "composed",
                "phased",
                "materialization_attempts",
            }
            for token in invocation.command
        )
        output = tmp_path / invocation.env[
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
        ]
        output.parent.mkdir(parents=True, exist_ok=True)
        output_bundle_bytes = b'{"approved":true}\n'
        output.write_bytes(output_bundle_bytes)
        provider_result = ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
        )
        provider_execution_results.append(provider_result)
        output_bundle_payloads.append(output_bundle_bytes)
        return provider_result

    with patch.dict(os.environ, {}, clear=True), patch.object(
        ProviderExecutor,
        "execute",
        execute_provider,
    ), patch.object(
        WorkflowExecutor,
        "_build_phased_provider_attempt_bindings",
        side_effect=AssertionError(
            "ordinary delivery entered phased route"
        ),
    ):
        completed = WorkflowExecutor(
            bundle,
            tmp_path,
            manager,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    assert len(invocations) == 1
    assert completed["status"] == "completed"
    assert completed["workflow_outputs"] == {"return__approved": True}
    [completed_step] = completed["steps"].values()
    binding = completed_step.get("debug", {}).get(
        "prompt_attempt_result_binding"
    )
    if target in {"2.22", "2.23"}:
        assert binding is not None
        assert binding["schema_version"] == (
            "workflow_prompt_attempt_result_binding.v1"
        )
        assert binding["attempt_ordinal"] == 1
    else:
        assert binding is None
    assert len(provider_execution_results) == 1
    assert len(output_bundle_payloads) == 1
    golden = _compatibility_golden_bytes(
        workspace=tmp_path,
        bundle=bundle,
        invocation=invocations[0],
        manager=manager,
        completed=completed,
        provider_execution_result=provider_execution_results[0],
        output_bundle_bytes=output_bundle_payloads[0],
    )
    expected_boundaries = {
        boundary
        for expected_case, boundary in EXPECTED_COMPATIBILITY_GOLDEN_BYTES
        if expected_case == case_key
    }
    assert set(golden) == expected_boundaries
    for boundary, actual_bytes in golden.items():
        identity = (case_key, boundary)
        assert actual_bytes == EXPECTED_COMPATIBILITY_GOLDEN_BYTES[
            identity
        ]
        assert _sha256(actual_bytes) == EXPECTED_COMPATIBILITY_SHA256[
            identity
        ]
