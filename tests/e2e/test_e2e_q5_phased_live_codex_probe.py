"""Q5 live-provider probe: real codex through the fixed phased instrumentation.

Opt-in (``ORCHESTRATE_E2E`` + codex CLI + auth) live probe that drives the
real ``PhasedProviderAttemptCoordinator`` / ``InteractiveTerminalTurnQueueAdapter``
/ ``PhasedSubmitEndpoint`` / ``ProviderPromptPhaseLedgerWriter`` stack with a
real interactive codex session instead of the scripted synthetic provider.
The scripted consumer-side validators force the invalid->valid retry cycle
(submission 1 rejected, submission 2 accepted), so a cooperating provider
produces the combined invalid-then-valid trace end to end.

This is diagnosis-grade instrumentation, not the Task-13 acceptance gate:
the prompt cut and validators are synthetic probe fixtures, not the migrated
target-2.23 consumer, so a pass here is explicitly NOT the combined consumer
proof and must not be cited as one (Q5 stop record governs).  Its value is
interpretability: with F1/F2 fixed, a stalled provider now yields a
deadline-terminalized ledger that validates offline, and a cooperating
provider proves the live seam works.

Evidence (result, elapsed, ledger rows, offline validation) is printed
unconditionally so a failing run carries its own diagnosis.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from orchestrator.providers.interactive_terminal import (
    InteractiveMemberInvocation,
    InteractiveSessionSupport,
)
from orchestrator.workflow.provider_phased_delivery.bindings import (
    AttemptComposition,
    PhasedProviderAttemptSuccess,
)
from orchestrator.workflow.provider_phased_delivery.frames import (
    render_initial_materialization_turn,
    render_retry_materialization_turn,
    render_task_turn,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    ByteDigestProjection,
    CompositionProjection,
)
from orchestrator.workflow.prompting import CanonicalPromptCut

from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e
from tests.test_provider_phased_delivery_coordinator import (
    _diagnostic,
    _digest,
)
from tests.test_q5_phased_synthetic_provider_diagnosis import (
    SyntheticProviderBindings,
    _ledger_rows,
    _run,
    _teardown_leaked_provider,
    _validation,
)

_PROBE_MODEL = "gpt-5.5"
_PROBE_EFFORT = "high"
_PROBE_TIMEOUT_SEC = 900.0

_TASK_SLICE = (
    "You are a provider inside a bounded diagnostic probe of the phased "
    "materialization protocol. Acknowledge briefly and wait; the "
    "materialization instructions arrive in the next message. Do not "
    "explore the repository and do not run anything yet.\n"
)
_MATERIALIZATION_SLICE = (
    "Materialization instructions (follow them exactly, nothing else):\n"
    "1. Run this shell command from the current working directory:\n"
    "   python3 -m orchestrator provider-materialization-submit\n"
    "2. It prints one JSON receipt line. If the receipt status is "
    '"retry_queued", run the same command exactly once more.\n'
    '3. When a receipt status is "accepted_closing", reply "done" and '
    "wait. Do not exit on your own; you will receive /exit when the "
    "session is over.\n"
)


def _probe_cut() -> CanonicalPromptCut:
    task = _TASK_SLICE.encode("utf-8")
    materialization = _MATERIALIZATION_SLICE.encode("utf-8")
    canonical = task + materialization
    return CanonicalPromptCut(
        task_slice=task,
        materialization_slice=materialization,
        canonical_composed=canonical,
        projection=CompositionProjection(
            canonical_composed=ByteDigestProjection(
                bytes=len(canonical),
                sha256=_digest(canonical),
            ),
            task_slice=ByteDigestProjection(
                bytes=len(task),
                sha256=_digest(task),
            ),
            materialization_slice=ByteDigestProjection(
                bytes=len(materialization),
                sha256=_digest(materialization),
            ),
        ),
    )


class LiveCodexBindings(SyntheticProviderBindings):
    """Synthetic-provider harness rewired to launch a real codex session."""

    def __init__(self, tmp_path: Path) -> None:
        super().__init__(
            tmp_path,
            mode="engage",
            timeout_sec=_PROBE_TIMEOUT_SEC,
            materialization_attempts=2,
            outcomes=((False, True), (True, True)),
        )
        cut = _probe_cut()
        task_turn = render_task_turn(cut=cut)
        initial_turn = render_initial_materialization_turn(
            cut=cut,
            submit_keys=("ENTER",),
        )
        retry_turn = render_retry_materialization_turn(
            cut=cut,
            submission_ordinal=2,
            diagnostics=(_diagnostic("output_validation_failed"),),
            submit_keys=("ENTER",),
        )
        codex_command = (
            "codex",
            "--model",
            _PROBE_MODEL,
            "--config",
            f"reasoning_effort={_PROBE_EFFORT}",
            "--dangerously-bypass-approvals-and-sandbox",
        )
        support = InteractiveSessionSupport(
            schema_version="interactive_terminal_turn_queue.v1",
            turn_boundary_messages=True,
            command=(*codex_command, "${PROMPT}"),
            message_submit_keys=("ENTER",),
            graceful_close_text="/exit",
            graceful_close_submit_keys=("ENTER",),
        )
        template = self.composition.invocation
        invocation = InteractiveMemberInvocation(
            invocation_id=template.invocation_id,
            member_id=template.member_id,
            attempt_scope_key=template.attempt_scope_key,
            attempt_ordinal=template.attempt_ordinal,
            resolved_command=(
                *codex_command,
                task_turn.delivered_turn.decode("utf-8"),
            ),
            cwd=template.cwd,
            env=dict(template.env),
            support=support,
        )
        self.composition = AttemptComposition(
            cut=cut,
            materialization_attempts=2,
            task_turn=task_turn,
            initial_materialization_turn=initial_turn,
            pre_prompt_command=(*codex_command, "${PROMPT}"),
            invocation=invocation,
            submit_binding=self.composition.submit_binding,
            endpoint_locator=self.composition.endpoint_locator,
            deadline=self.composition.deadline,
        )
        self.offered_turns = (initial_turn, retry_turn)


@pytest.mark.e2e
def test_live_codex_completes_combined_invalid_then_valid_probe(
    tmp_path: Path,
) -> None:
    """Real codex drives the phased invalid->valid spine under the fixed stack.

    On a stall, the F1/F2 fixes guarantee the printed ledger carries the
    deadline terminalization rows and validates offline, so a failure here
    is directly interpretable provider-behavior evidence.
    """

    skip_if_no_e2e()
    skip_if_no_cli("codex")

    bindings = LiveCodexBindings(tmp_path)
    started_wall = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        result, elapsed, _finished = _run(bindings)
        rows = _ledger_rows(bindings)
        validation = _validation(bindings)
        print(
            json.dumps(
                {
                    "probe": "q5-phased-live-codex",
                    "model": _PROBE_MODEL,
                    "effort": _PROBE_EFFORT,
                    "started_utc": started_wall,
                    "elapsed_sec": round(elapsed, 2),
                    "result_type": type(result).__name__,
                    "first_diagnostic": (
                        None
                        if type(result) is PhasedProviderAttemptSuccess
                        else result.first_diagnostic.reason
                    ),
                    "ledger_events": [
                        row["event"]
                        for row in rows
                        if row.get("record_kind") == "event"
                    ],
                    "ledger_validation": validation,
                },
                indent=2,
            )
        )
        # Ledger evidence must validate offline in BOTH outcomes (F1/F2).
        assert validation["status"] == "complete"
        # The probe's acceptance-relevant signal: the combined
        # invalid->valid cycle completed against a live provider.
        assert type(result) is PhasedProviderAttemptSuccess
        assert result.submission_ordinal == 2
        assert validation["terminal_event"] == "publication_succeeded"
    finally:
        _teardown_leaked_provider(bindings)
