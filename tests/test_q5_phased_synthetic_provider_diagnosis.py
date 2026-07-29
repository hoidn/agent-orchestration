"""Q5 diagnosis: real coordinator + real turn-queue adapter + scripted provider.

Provider-free replay of the Q5 real-provider acceptance seam (task brief:
docs/plans/2026-07-28-q5-phased-turn-queue-coordinator-diagnosis-task.md).

Every test drives the real ``PhasedProviderAttemptCoordinator`` through the
real ``InteractiveTerminalTurnQueueAdapter`` (real tmux backend), the real
``PhasedSubmitEndpoint`` over a real unix socket, the real
``ProviderPromptPhaseLedgerWriter``, and the production ``AWAITING_SUBMIT``
polling loop (``_WorkflowPhasedProviderAttemptBindings.receive_attempt_event``).
The provider side of the turn queue is a deterministic synthetic script that
runs inside the tmux pane and submits through the production
``submit_materialization`` helper, so the turn-queue capability boundary is
never bypassed.

Wait-state ids (W*) refer to the enumeration in
docs/plans/2026-07-28-q5-phased-diagnosis-report.md.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from orchestrator.providers.interactive_terminal import (
    InteractiveMemberInvocation,
    InteractiveSessionSupport,
    InteractiveTerminalError,
    InteractiveTerminalTurnQueueAdapter,
)
from orchestrator.workflow.provider_phased_delivery.bindings import (
    AttemptAllocation,
    AttemptComposition,
    PhasedProviderAttemptFailure,
    PhasedProviderAttemptSuccess,
)
from orchestrator.workflow.provider_phased_delivery.coordinator import (
    PhasedProviderAttemptCoordinator,
)
from orchestrator.workflow.provider_phased_delivery.endpoint import (
    PhasedSubmitEndpoint,
)
from orchestrator.workflow.provider_phased_delivery.ledger import (
    ProviderPromptPhaseLedgerWriter,
    validate_ledger_bytes,
)
from orchestrator.workflow.provider_phased_delivery.protocol import (
    PHASED_PROVIDER_BINDING_ENV,
    derive_submit_binding_and_locator,
)
from orchestrator.workflow.provider_phased_delivery.runtime_bindings import (
    _WorkflowPhasedAdapter,
    _WorkflowPhasedProviderAttemptBindings,
)

from tests.test_provider_phased_delivery_coordinator import (
    RecordingBindings,
    _invocation,
)

_CLONE_ROOT = Path(__file__).resolve().parent.parent

_PROVIDER_SCRIPT = '''\
"""Deterministic synthetic provider for Q5 phased-delivery diagnosis."""
import sys
import time

sys.path.insert(0, {clone_root!r})

from orchestrator.workflow.provider_phased_delivery.protocol import (
    PhasedSubmitProtocolClosedError,
    decode_submit_binding,
    submit_materialization,
)

MODE = sys.argv[1]
BINDING = decode_submit_binding()


def submit(ordinal):
    guard = BINDING.deadline + 10.0
    while True:
        try:
            return submit_materialization(
                request_id="synthetic-%s-%d" % (MODE, ordinal),
            )
        except PhasedSubmitProtocolClosedError:
            if time.monotonic() >= guard:
                sys.exit(3)
            time.sleep(0.05)


def sleep_forever():
    while True:
        time.sleep(0.5)


if MODE == "never-engage":
    sleep_forever()
elif MODE == "exit-after-first-turn":
    sys.stdin.readline()
    sys.exit(7)
elif MODE == "silent-after-first":
    submit(1)
    sleep_forever()
elif MODE in ("engage", "refuse-close"):
    receipt = submit(1)
    if receipt.status == "retry_queued":
        receipt = submit(2)
    if MODE == "refuse-close":
        sleep_forever()
    sys.exit(0 if receipt.status == "accepted_closing" else 5)
else:
    sys.exit(4)
'''


class SyntheticProviderBindings(RecordingBindings):
    """RecordingBindings with the adapter/endpoint/ledger/clock made real.

    Candidate snapshot/validation/freeze/commit bindings stay scripted (they
    are consumer-side and not under diagnosis); everything on the
    coordinator<->provider seam is the production implementation.
    """

    def __init__(
        self,
        tmp_path: Path,
        *,
        mode: str,
        timeout_sec: float,
        materialization_attempts: int = 2,
        outcomes: tuple[tuple[bool, bool], ...] = (
            (False, True),
            (True, True),
        ),
    ) -> None:
        super().__init__(
            materialization_attempts=materialization_attempts,
            outcomes=outcomes,
        )
        self.run_root = tmp_path / "run"
        self.run_root.mkdir()
        script_path = tmp_path / "synthetic_provider.py"
        script_path.write_text(
            _PROVIDER_SCRIPT.format(clone_root=str(_CLONE_ROOT)),
            encoding="utf-8",
        )
        # AF_UNIX socket paths are length-capped (~107 bytes); pytest tmp
        # paths are too long, so sockets live in a short mkdtemp directory.
        self.socket_dir = Path(tempfile.mkdtemp(prefix="q5d-"))
        deadline = time.monotonic() + timeout_sec
        binding, locator = derive_submit_binding_and_locator(
            attempt_scope_sha256=self.allocation.scope.key,
            socket_root=self.socket_dir,
            nonce="q5-diagnosis",
            deadline=deadline,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in {"TMUX", "PYTHONPATH"}
        }
        env[PHASED_PROVIDER_BINDING_ENV] = binding.opaque_value
        env["PYTHONPATH"] = str(_CLONE_ROOT)
        support = InteractiveSessionSupport(
            schema_version="interactive_terminal_turn_queue.v1",
            turn_boundary_messages=True,
            command=(sys.executable, str(script_path), mode, "${PROMPT}"),
            message_submit_keys=("ENTER",),
            graceful_close_text="/exit",
            graceful_close_submit_keys=("ENTER",),
        )
        template = _invocation(self.composition.task_turn, binding)
        invocation = InteractiveMemberInvocation(
            invocation_id=template.invocation_id,
            member_id=template.member_id,
            attempt_scope_key=template.attempt_scope_key,
            attempt_ordinal=template.attempt_ordinal,
            resolved_command=(
                sys.executable,
                str(script_path),
                mode,
                self.composition.task_turn.delivered_turn.decode("utf-8"),
            ),
            cwd=_CLONE_ROOT,
            env=env,
            support=support,
        )
        self.composition = AttemptComposition(
            cut=self.composition.cut,
            materialization_attempts=materialization_attempts,
            task_turn=self.composition.task_turn,
            initial_materialization_turn=(
                self.composition.initial_materialization_turn
            ),
            pre_prompt_command=(
                sys.executable,
                str(script_path),
                mode,
                "${PROMPT}",
            ),
            invocation=invocation,
            submit_binding=binding,
            endpoint_locator=locator,
            deadline=deadline,
        )
        self.real_adapter = InteractiveTerminalTurnQueueAdapter(
            runtime_root=tmp_path / "adapter",
            socket_root=self.socket_dir,
            poll_interval_sec=0.05,
            operation_timeout_sec=5.0,
        )
        self.adapter = _WorkflowPhasedAdapter(self.real_adapter)
        self.endpoint = PhasedSubmitEndpoint(
            binding=binding,
            locator=locator,
            configured_total=materialization_attempts,
        )
        self.ledger_path: Path | None = None

    def monotonic_now(self) -> float:
        return time.monotonic()

    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> ProviderPromptPhaseLedgerWriter:
        self.actions.append("ledger.header")
        writer = ProviderPromptPhaseLedgerWriter.create(
            self.run_root,
            scope=allocation.scope,
            ordinal=allocation.attempt_ordinal,
            cut=composition.cut,
            materialization_attempts=composition.materialization_attempts,
            created_at=self.observed_at(),
        )
        self.ledger_path = writer.path
        return writer

    def create_endpoint(
        self,
        composition: AttemptComposition,
    ) -> PhasedSubmitEndpoint:
        assert composition == self.composition
        self.actions.append("bindings.endpoint")
        return self.endpoint

    def receive_attempt_event(self, *, boundary, endpoint, deadline):
        # Production AWAITING_SUBMIT loop: 50ms slices, liveness probes,
        # whole-attempt deadline event. Only needs ``self.adapter``.
        return _WorkflowPhasedProviderAttemptBindings.receive_attempt_event(
            self,  # type: ignore[arg-type]
            boundary=boundary,
            endpoint=endpoint,
            deadline=deadline,
        )


def _run(bindings: SyntheticProviderBindings):
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator
    started = time.monotonic()
    try:
        result = coordinator.run()
    finally:
        finished = time.monotonic()
    return result, finished - started, finished


def _ledger_rows(bindings: SyntheticProviderBindings) -> list[dict]:
    assert bindings.ledger_path is not None
    return [
        json.loads(line)
        for line in bindings.ledger_path.read_bytes().splitlines()
    ]


def _events(rows: list[dict]) -> list[str]:
    return [row["event"] for row in rows if row.get("record_kind") == "event"]


def _validation(bindings: SyntheticProviderBindings) -> dict:
    assert bindings.ledger_path is not None
    return validate_ledger_bytes(bindings.ledger_path.read_bytes())


def _provider_survivor_alive(bindings: SyntheticProviderBindings) -> bool:
    adapter = bindings.real_adapter
    try:
        return adapter._backend.server_alive(
            adapter._socket_path,
            adapter._session_name,
            timeout_sec=3.0,
        )
    except InteractiveTerminalError:
        return False


def _teardown_leaked_provider(bindings: SyntheticProviderBindings) -> None:
    """Reap tmux/pane survivors the post-expiry terminalizer never aborts."""

    adapter = bindings.real_adapter
    handle = bindings.adapter.active_handle
    if handle is not None:
        try:
            adapter.abort(handle, time.monotonic() + 10.0)
        except InteractiveTerminalError:
            pass
    try:
        if adapter._backend.server_alive(
            adapter._socket_path,
            adapter._session_name,
            timeout_sec=3.0,
        ):
            adapter._backend.close_server(
                adapter._socket_path,
                timeout_sec=5.0,
            )
    except InteractiveTerminalError:
        pass
    shutil.rmtree(bindings.socket_dir, ignore_errors=True)


_PRE_SUBMIT_EVENTS = [
    "task_start_requested",
    "task_started",
    "turn_offer_requested",
    "turn_offered",
]


def test_synthetic_provider_completes_invalid_then_valid_spine(
    tmp_path: Path,
) -> None:
    """Baseline: the full invalid->valid consumer gate passes provider-free.

    Exercises W-A1 start, W-A2 offer, W-E1 receive_event, W-E2 resolve,
    W-A3 offer_close, W-A5 join, W-E3 shutdown, all inside their deadlines.
    """

    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="engage",
        timeout_sec=60.0,
    )
    try:
        result, elapsed, _finished = _run(bindings)
        assert type(result) is PhasedProviderAttemptSuccess
        assert elapsed < 30.0
        assert result.submission_ordinal == 2
        validation = _validation(bindings)
        assert validation["status"] == "complete"
        assert validation["terminal_event"] == "publication_succeeded"
        events = _events(_ledger_rows(bindings))
        assert events == _PRE_SUBMIT_EVENTS + [
            "submit_received",
            "validation_rejected",
            "candidate_reset",
            "retry_queued",
            "turn_offer_requested",
            "turn_offered",
            "submit_received",
            "candidate_frozen",
            "close_offer_requested",
            "close_offered",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "join_started",
            "join_succeeded",
            "publication_started",
            "publication_succeeded",
        ]
        # Natural shutdown proved: no survivors to reap.
        assert not _provider_survivor_alive(bindings)
    finally:
        _teardown_leaked_provider(bindings)


def test_never_engaging_provider_bounds_wait_at_whole_attempt_deadline(
    tmp_path: Path,
) -> None:
    """Failure shape (a), 2026-07-27/28: provider never engages the handshake.

    W-R1 (AWAITING_SUBMIT loop) must terminate at the whole-attempt deadline
    and surface a structured deadline outcome.  Post-F1, the fail-safe
    terminalization rows also land in the ledger, so the run is
    distinguishable from a healthy long wait; the zero-call cleanup rule
    still applies, so the provider pane/server survive for the operator.
    """

    timeout_sec = 6.0
    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="never-engage",
        timeout_sec=timeout_sec,
    )
    try:
        result, _elapsed, finished = _run(bindings)
        # Totality: the wait ended at the whole-attempt deadline, not later.
        deadline = bindings.composition.deadline
        assert deadline <= finished < deadline + 4.0
        assert type(result) is PhasedProviderAttemptFailure
        assert result.first_diagnostic.reason == (
            "deadline_exhausted_during_submit"
        )
        assert result.lifecycle.phase == "FAILED"
        # Designed post-expiry zero-call cleanup: no abort was attempted...
        assert result.lifecycle.abort_calls == 0
        assert result.lifecycle.provider_cleanup == "INCOMPLETE"
        assert result.cleanup_diagnostic is not None
        assert result.cleanup_diagnostic.reason == (
            "deadline_exhausted_before_adapter_cleanup"
        )
        assert result.terminalization_tier == "T1"
        # ...so the synthetic provider demonstrably survives the attempt.
        assert _provider_survivor_alive(bindings)
        # F1 fixed: the fail-safe terminalization rows land post-expiry,
        # replacing the silent five-row prefix observed on 2026-07-27/28.
        rows = _ledger_rows(bindings)
        assert _events(rows) == _PRE_SUBMIT_EVENTS + [
            "cleanup_finished",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "terminal_failed",
        ]
        validation = _validation(bindings)
        assert validation["status"] == "complete"
        assert validation["reason"] == "complete"
        assert validation["terminal_event"] == "terminal_failed"
    finally:
        _teardown_leaked_provider(bindings)


def test_mid_phase_silent_provider_bounds_wait_and_records_terminalization(
    tmp_path: Path,
) -> None:
    """Failure shape (b): provider engages, then goes silent mid-phase.

    The retry wait (second AWAITING_SUBMIT visit, W-R1) must also be
    deadline-bounded, and post-F1/F2 the ledger records the terminalization
    tail after the last healthy row (``turn_offered``) and validates
    offline.
    """

    timeout_sec = 8.0
    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="silent-after-first",
        timeout_sec=timeout_sec,
    )
    try:
        result, _elapsed, finished = _run(bindings)
        deadline = bindings.composition.deadline
        assert deadline <= finished < deadline + 4.0
        assert type(result) is PhasedProviderAttemptFailure
        assert result.first_diagnostic.reason == (
            "deadline_exhausted_during_submit"
        )
        assert result.lifecycle.abort_calls == 0
        assert result.lifecycle.provider_cleanup == "INCOMPLETE"
        assert _provider_survivor_alive(bindings)
        events = _events(_ledger_rows(bindings))
        assert events == _PRE_SUBMIT_EVENTS + [
            "submit_received",
            "validation_rejected",
            "candidate_reset",
            "retry_queued",
            "turn_offer_requested",
            "turn_offered",
            "cleanup_finished",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "terminal_failed",
        ]
        validation = _validation(bindings)
        assert validation["status"] == "complete"
        assert validation["terminal_event"] == "terminal_failed"
    finally:
        _teardown_leaked_provider(bindings)


def test_provider_exit_before_submit_surfaces_and_terminalizes_fast(
    tmp_path: Path,
) -> None:
    """A dead provider is detected promptly and surfaces full terminal rows.

    Discriminates H3-death from the observed silence: had the 2026-07-27
    provider process actually died mid-wait, the liveness probe (W-R1) would
    have produced ``provider_exited_before_submit`` plus a complete
    terminalization ledger within seconds -- not an hour of silence.
    """

    timeout_sec = 30.0
    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="exit-after-first-turn",
        timeout_sec=timeout_sec,
    )
    try:
        result, elapsed, _finished = _run(bindings)
        assert elapsed < 10.0
        assert type(result) is PhasedProviderAttemptFailure
        assert result.first_diagnostic.reason == (
            "provider_exited_before_submit"
        )
        # Pre-expiry terminalization works: abort ran, rows landed.
        assert result.lifecycle.abort_calls == 1
        assert result.lifecycle.provider_cleanup == "COMPLETE"
        events = _events(_ledger_rows(bindings))
        assert events == _PRE_SUBMIT_EVENTS + [
            "cleanup_finished",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "terminal_failed",
        ]
        validation = _validation(bindings)
        assert validation["terminal_event"] == "terminal_failed"
        assert not _provider_survivor_alive(bindings)
    finally:
        _teardown_leaked_provider(bindings)


def test_exhausted_attempts_aborts_live_provider_and_surfaces_terminal_rows(
    tmp_path: Path,
) -> None:
    """Pre-expiry terminalization on a live provider: abort + full rows.

    With budget remaining, the terminalizer aborts the live pane (W-A6) and
    the ledger records the full terminalization production.  Post-F2, the
    truthful evidence also validates offline even though the exhausted
    submission was resolved with a terminal ``failed`` receipt (zero
    drainage at shutdown is legal in the terminalizing context).
    """

    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="engage",
        timeout_sec=60.0,
        materialization_attempts=1,
        outcomes=((False, True),),
    )
    try:
        result, elapsed, _finished = _run(bindings)
        assert elapsed < 30.0
        assert type(result) is PhasedProviderAttemptFailure
        assert result.first_diagnostic.reason == (
            "materialization_attempts_exhausted"
        )
        assert result.lifecycle.abort_calls == 1
        assert result.lifecycle.provider_cleanup == "COMPLETE"
        events = _events(_ledger_rows(bindings))
        assert events == _PRE_SUBMIT_EVENTS + [
            "submit_received",
            "validation_rejected",
            "candidate_reset",
            "cleanup_finished",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "terminal_failed",
        ]
        validation = _validation(bindings)
        assert validation["status"] == "complete"
        assert validation["reason"] == "complete"
        assert validation["terminal_event"] == "terminal_failed"
        assert not _provider_survivor_alive(bindings)
    finally:
        _teardown_leaked_provider(bindings)


def test_exhausted_attempts_ledger_should_validate_offline(
    tmp_path: Path,
) -> None:
    """F2 regression: truthful terminalization evidence validates offline.

    Was the strict-xfail fixture of the 2026-07-28 diagnosis: the endpoint
    counts only ``accepted_closing`` receipts toward
    ``active_requests_drained``, so the validator's drain requirement now
    applies only to the normal close-path shutdown, not to terminalizing
    shutdowns whose submissions were resolved with terminal receipts.
    """

    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="engage",
        timeout_sec=60.0,
        materialization_attempts=1,
        outcomes=((False, True),),
    )
    try:
        result, _elapsed, _finished = _run(bindings)
        assert type(result) is PhasedProviderAttemptFailure
        validation = _validation(bindings)
        assert validation["status"] == "complete"
        assert validation["terminal_event"] == "terminal_failed"
    finally:
        _teardown_leaked_provider(bindings)


def test_close_refusing_provider_bounds_join_and_records_terminalization(
    tmp_path: Path,
) -> None:
    """W-A5: a provider that never exits after close bounds at the deadline.

    The join poll loop must terminate at the whole-attempt deadline; post-F1
    the terminalizer records the join-expiry tail (``cleanup_finished`` with
    the zero-call expiry diagnostic, then ``terminal_failed``) after
    ``join_started``.
    """

    timeout_sec = 10.0
    bindings = SyntheticProviderBindings(
        tmp_path,
        mode="refuse-close",
        timeout_sec=timeout_sec,
    )
    try:
        result, _elapsed, finished = _run(bindings)
        deadline = bindings.composition.deadline
        assert deadline <= finished < deadline + 4.0
        assert type(result) is PhasedProviderAttemptFailure
        assert result.first_diagnostic.reason == (
            "deadline_exhausted_during_join"
        )
        assert result.lifecycle.abort_calls == 0
        assert result.endpoint_shutdown_status == "complete"
        events = _events(_ledger_rows(bindings))
        assert events == _PRE_SUBMIT_EVENTS + [
            "submit_received",
            "validation_rejected",
            "candidate_reset",
            "retry_queued",
            "turn_offer_requested",
            "turn_offered",
            "submit_received",
            "candidate_frozen",
            "close_offer_requested",
            "close_offered",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "join_started",
            "cleanup_finished",
            "terminal_failed",
        ]
        validation = _validation(bindings)
        assert validation["status"] == "complete"
        assert validation["terminal_event"] == "terminal_failed"
        assert _provider_survivor_alive(bindings)
    finally:
        _teardown_leaked_provider(bindings)
