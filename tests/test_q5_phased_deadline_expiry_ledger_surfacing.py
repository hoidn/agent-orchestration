"""Q5 diagnosis: deterministic post-expiry terminalization surfacing checks.

Isolates the H2 finding of
docs/plans/2026-07-28-q5-phased-diagnosis-report.md with a frozen clock and
no tmux: once the whole-attempt deadline expires inside the submit wait,
``PhasedProviderAttemptCoordinator._append`` admits ``ledger_append`` against
that same expired deadline, so every terminalization row
(``cleanup_finished``, ``ingress_shutdown_*``, ``terminal_failed``) is
refused, and ``_safe_append`` swallows the refusal.  The ledger therefore
keeps the healthy five-row pre-submit prefix -- indistinguishable from a
still-waiting attempt -- while the returned failure object alone carries the
deadline diagnostic.

The design requires otherwise: the fail-safe terminalizer is "the only
exception" to the zero-call rule and still *emits* its ledger rows with no
remaining budget (workflow_lisp_phased_contract_delivery.md, "Deadline
observation discipline" / T0-T3 terminalization productions).  The strict
xfail below asserts that contract and is the ready-made regression test for
the fix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    """Current behavior, pinned: expiry surfaces ONLY in the returned object.

    The failure object is fully populated (structured outcome exists), the
    designed zero-call rule skips the abort, and the fake endpoint is still
    shut down.  This is the deterministic mechanics behind the two observed
    acceptance failures.
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


def test_post_expiry_terminalization_leaves_healthy_looking_ledger_prefix(
    tmp_path: Path,
) -> None:
    """H2 mechanics, pinned: every terminal row is dropped after expiry.

    ``_admit_deadline("ledger_append")`` refuses each terminalization append
    against the already-expired attempt deadline and ``_safe_append``
    swallows the refusal, so the ledger ends exactly at the five-row
    pre-submit prefix and offline validation reports a healthy
    ``valid_prefix`` -- the shape observed on 2026-07-27 and recorded by the
    Task-13 stop record on 2026-07-28.
    """

    bindings, _result, rows, events = _run_expired(tmp_path)
    assert len(rows) == 5
    assert events == [
        "task_start_requested",
        "task_started",
        "turn_offer_requested",
        "turn_offered",
    ]
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["status"] == "valid_prefix"
    assert validation["reason"] == "nonterminal_prefix"
    assert validation["terminal_event"] is None


@pytest.mark.xfail(
    strict=True,
    reason=(
        "H2 defect (Q5 diagnosis 2026-07-28): the design's fail-safe "
        "terminalization must emit cleanup_finished / ingress_shutdown_* / "
        "terminal_failed with no remaining budget, but _append gates every "
        "row behind a ledger_append admission against the already-expired "
        "whole-attempt deadline, so the T2a production never reaches the "
        "ledger.  Remove this xfail with the fix; these assertions are the "
        "regression test."
    ),
)
def test_post_expiry_terminalization_emits_failsafe_ledger_rows(
    tmp_path: Path,
) -> None:
    """Design contract: deadline expiry must surface in the phase ledger."""

    bindings, _result, _rows, events = _run_expired(tmp_path)
    assert "cleanup_finished" in events
    assert (
        "ingress_shutdown_finished" in events
        or "ingress_shutdown_failed" in events
    )
    assert events[-1] == "terminal_failed"
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["terminal_event"] == "terminal_failed"
