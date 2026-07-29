"""Q5: post-expiry fail-safe terminalization must surface in the phase ledger.

Regression tests for finding F1 of
docs/plans/2026-07-28-q5-phased-diagnosis-report.md: once the whole-attempt
deadline expires inside the submit wait, the fail-safe terminalizer is the
design's sole exception to the zero-call rule
(workflow_lisp_phased_contract_delivery.md, "Deadline observation
discipline" / T0-T3 terminalization productions) — it makes no further
adapter calls, but it still *emits* its ledger rows (``cleanup_finished``,
``ingress_shutdown_*``, ``terminal_failed``) with no remaining budget, so a
deadline-terminalized attempt is distinguishable from a healthy long wait.

Before the fix, ``PhasedProviderAttemptCoordinator._append`` admitted a
``ledger_append`` deadline operation against the already-expired attempt
deadline for these rows too, and ``_safe_append`` swallowed the refusal: the
ledger froze at the healthy five-row pre-submit prefix — the silent-ledger
shape observed in the 2026-07-27 acceptance attempt and recorded by the
2026-07-28 Task-13 stop record.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.workflow.provider_phased_delivery.bindings import (
    AttemptAllocation,
    AttemptComposition,
    PhasedProviderAttemptFailure,
    SerializedAttemptEvent,
)
from orchestrator.workflow.provider_phased_delivery.coordinator import (
    PhasedProviderAttemptCoordinator,
)
from orchestrator.workflow.provider_phased_delivery.ledger import (
    ProviderPromptPhaseLedgerWriter,
    validate_ledger_bytes,
)

from tests.test_provider_phased_delivery_coordinator import RecordingBindings


class ExpiringSubmitWaitBindings(RecordingBindings):
    """The submit wait consumes the whole attempt budget, then reports it.

    Models exactly what the production ``AWAITING_SUBMIT`` loop does when the
    provider never submits (proven against the real loop by
    test_q5_phased_synthetic_provider_diagnosis.py): the clock reaches the
    whole-attempt deadline inside the wait and the loop returns a
    ``deadline`` event.  Everything else is the standard recording harness
    with the real on-disk ledger writer.
    """

    def __init__(self, tmp_path: Path) -> None:
        super().__init__(materialization_attempts=1, outcomes=((True, True),))
        self.now = 0.0
        self.run_root = tmp_path / "run"
        self.run_root.mkdir()
        self.ledger_path: Path | None = None

    def monotonic_now(self) -> float:
        return self.now

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

    def receive_attempt_event(self, *, boundary, endpoint, deadline):
        if boundary != "AWAITING_SUBMIT":
            self.actions.append(f"bindings.control_event.{boundary}.none")
            return None
        self.now = self.composition.deadline
        return SerializedAttemptEvent(kind="deadline")


def _run_expired(tmp_path: Path):
    bindings = ExpiringSubmitWaitBindings(tmp_path)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator
    result = coordinator.run()
    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "deadline_exhausted_during_submit"
    assert bindings.ledger_path is not None
    rows = [
        json.loads(line)
        for line in bindings.ledger_path.read_bytes().splitlines()
    ]
    events = [
        row["event"] for row in rows if row.get("record_kind") == "event"
    ]
    return bindings, result, rows, events


def test_post_expiry_terminalization_returns_structured_failure_but_skips_cleanup(
    tmp_path: Path,
) -> None:
    """Zero-call rule unchanged: expiry skips the abort, endpoint fail-safe runs.

    The failure object is fully populated; the adapter is never asked to
    abort after expiry (designed fail-closed cleanup skip), and the
    coordinator-local endpoint fail-safe still shuts ingress down.
    """

    bindings, result, _rows, _events = _run_expired(tmp_path)
    # Coordinator labels this tier "T1": terminalizing ingress shutdown had
    # not started when the tier was sampled at _terminalize entry.
    assert result.terminalization_tier == "T1"
    assert result.lifecycle.phase == "FAILED"
    assert result.lifecycle.provider_cleanup == "INCOMPLETE"
    assert result.lifecycle.abort_calls == 0
    assert result.cleanup_diagnostic is not None
    assert result.cleanup_diagnostic.reason == (
        "deadline_exhausted_before_adapter_cleanup"
    )
    # Zero-call rule: the adapter was never asked to abort.
    assert "adapter.abort" not in bindings.actions
    # Endpoint fail-safe still ran (coordinator-local, non-adapter).
    assert "endpoint.stop" in bindings.actions
    assert "endpoint.shutdown" in bindings.actions
    assert result.endpoint_shutdown_status == "complete"
    assert bindings.failure_finalization_calls == 1


def test_post_expiry_terminalization_records_failsafe_rows_in_ledger(
    tmp_path: Path,
) -> None:
    """F1 regression: the fail-safe rows land after whole-attempt expiry.

    The terminalization production continues past the pre-submit prefix and
    the rows tell the truth: cleanup was skipped by the zero-call rule
    (``incomplete``, zero abort calls, the supplemental expiry diagnostic)
    and the endpoint fail-safe completed.
    """

    _bindings, _result, rows, events = _run_expired(tmp_path)
    assert events == [
        "task_start_requested",
        "task_started",
        "turn_offer_requested",
        "turn_offered",
        "cleanup_finished",
        "ingress_shutdown_started",
        "ingress_shutdown_finished",
        "terminal_failed",
    ]
    cleanup_payload = rows[5]["payload"]
    assert cleanup_payload["cleanup_status"] == "incomplete"
    assert cleanup_payload["abort_calls"] == 0
    assert cleanup_payload["provider_cleanup_proof"] is None
    assert cleanup_payload["cleanup_diagnostic"]["reason"] == (
        "deadline_exhausted_before_adapter_cleanup"
    )
    terminal_payload = rows[8]["payload"]
    assert terminal_payload["diagnostic"]["reason"] == (
        "deadline_exhausted_during_submit"
    )
    assert terminal_payload["cleanup_status"] == "incomplete"
    assert terminal_payload["endpoint_shutdown_status"] == "complete"
    assert terminal_payload["natural_shutdown_proof"] is None


def test_post_expiry_terminalization_emits_failsafe_ledger_rows(
    tmp_path: Path,
) -> None:
    """F1 contract: deadline expiry must surface in the phase ledger.

    Was the strict-xfail fixture of the 2026-07-28 diagnosis; now the
    regression test for the fix.
    """

    bindings, _result, _rows, events = _run_expired(tmp_path)
    assert "cleanup_finished" in events
    assert (
        "ingress_shutdown_finished" in events
        or "ingress_shutdown_failed" in events
    )
    assert events[-1] == "terminal_failed"
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["status"] == "complete"
    assert validation["reason"] == "complete"
    assert validation["terminal_event"] == "terminal_failed"
