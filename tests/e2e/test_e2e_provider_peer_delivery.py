"""Real Codex proof for recorded natural turn-boundary peer delivery."""

from __future__ import annotations

from argparse import Namespace
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import time
from types import MappingProxyType
from typing import Sequence

import pytest

from orchestrator.providers import interactive_terminal as interactive_terminal_module
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.report import report_workflow
from orchestrator.contracts.output_contract import validate_output_bundle
from orchestrator.providers import (
    InteractiveSessionSupport,
    ProviderExecutor,
    ProviderRegistry,
)
from orchestrator.providers.interactive_terminal import (
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalError,
    InteractiveTerminalStartOutcome,
    InteractiveTerminalTurnQueueAdapter,
    NaturalShutdownProof,
    NoBackendAllocationProof,
    PaneProcessStatus,
    PhasedFailedCleanupEvidence,
    project_phased_failed_cleanup_evidence,
)
from orchestrator.workflow.provider_peer_group.bindings import (
    PeerDeliveryFrame,
)
from orchestrator.workflow.provider_peer_group.ledger import (
    PeerMessageLedger,
    inspect_peer_message_ledger,
)
from orchestrator.workflow.provider_peer_group.models import (
    FrozenPeerMemberResult,
    PeerAcknowledgeReceipt,
    PeerAcknowledgeRequest,
    PeerAttemptIdentity,
    PeerEndpointIdentity,
    PeerFinishReceipt,
    PeerFinishRequest,
    PeerGroupTerminalEvidence,
    PeerGroupVisitIdentity,
    PeerReadyReceipt,
    PeerReadyRequest,
)
from orchestrator.workflow.provider_peer_group.paths import (
    realize_provider_peer_group_paths,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    PeerProtocolEvent,
    PeerProtocolListener,
)
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e


_EXPECTED_VALUE = "peer-delivery-ok"
_MESSAGE_ID = "real-adapter-message-1"
_SECOND_MESSAGE_ID = "real-adapter-message-2"
_TASK_ACTION_MARKER_ENV = "ORCHESTRATE_E2E_TASK_ACTION_MARKER"
_TASK_ACTION_RELEASE_ENV = "ORCHESTRATE_E2E_TASK_ACTION_RELEASE"
_FIRST_OFFER_MARKER_ENV = "ORCHESTRATE_E2E_FIRST_OFFER_MARKER"
_FIRST_OFFER_RELEASE_ENV = "ORCHESTRATE_E2E_FIRST_OFFER_RELEASE"
_SECOND_OFFER_MARKER_ENV = "ORCHESTRATE_E2E_SECOND_OFFER_MARKER"
_SECOND_OFFER_RELEASE_ENV = "ORCHESTRATE_E2E_SECOND_OFFER_RELEASE"
_EVENT_TIMEOUT_SEC = 240.0
_REPO_ROOT = Path(__file__).parents[2]
_COORDINATOR_MESSAGE = (
    "Preserve this exact peer payload 🌍.\nSecond line: Ω"
)
_COORDINATOR_SENDER_VALUE = "peer-send-complete"
_ROLE_PROMPT_FIXTURES = {
    "sender": "real_peer_two_sender.md",
    "receiver": "real_peer_two_receiver.md",
}
_THREE_MEMBER_FIXTURES = {
    "source": "real_peer_group_three.orc",
    "providers": "real_peer_group_three.providers.json",
    "prompts": "real_peer_group_three.prompts.json",
}
_THREE_MEMBER_ROLE_PROMPTS = {
    "sender": "real_peer_group_sender.md",
    "receiver": "real_peer_group_receiver.md",
    "witness": "real_peer_group_witness.md",
}


class _P2Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value

    def wait(self, duration: float) -> None:
        self.value += duration


class _P2StartBackend:
    """Controlled backend used only to execute P2's closed start fixtures."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.actions: list[str] = []
        self.server_live = False
        self.pane_live = False

    def start_server(
        self,
        socket_path: Path,
        session_name: str,
        *,
        env: dict[str, str],
        timeout_sec: float,
    ) -> None:
        del socket_path, session_name, env, timeout_sec
        self.actions.append("start_server")
        self.server_live = True
        if self.mode in {"complete_failure", "incomplete_failure"}:
            raise InteractiveTerminalError("server_start_failed")

    def start_pane(
        self,
        socket_path: Path,
        session_name: str,
        command: Sequence[str],
        *,
        cwd: Path | None,
        exit_status_path: Path,
        timeout_sec: float,
    ) -> str:
        del socket_path, session_name, command, cwd, exit_status_path, timeout_sec
        self.actions.append("start_pane")
        self.pane_live = True
        return "p2-pane"

    def pane_process_status(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> PaneProcessStatus:
        del socket_path, target, timeout_sec
        self.actions.append("pane_process_status")
        return PaneProcessStatus(
            state="running" if self.pane_live else "missing",
            return_code=None,
        )

    def server_alive(
        self,
        socket_path: Path,
        session_name: str,
        *,
        timeout_sec: float,
    ) -> bool:
        del socket_path, session_name, timeout_sec
        self.actions.append("server_alive")
        return self.server_live

    def offer_literal(
        self,
        socket_path: Path,
        target: str,
        literal_text: str,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, target, literal_text, timeout_sec
        self.actions.append("offer_literal")

    def offer_keys(
        self,
        socket_path: Path,
        target: str,
        keys: Sequence[str],
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, target, keys, timeout_sec
        self.actions.append("offer_keys")

    def close_pane(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, target, timeout_sec
        self.actions.append("close_pane")
        self.pane_live = False

    def close_server(
        self,
        socket_path: Path,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, timeout_sec
        self.actions.append("close_server")
        if self.mode == "incomplete_failure":
            raise InteractiveTerminalError("server_teardown_failed")
        self.server_live = False


class _RecordingProductionBackend:
    """Delegate to the production tmux backend while recording call bounds."""

    def __init__(self) -> None:
        self._delegate = (
            interactive_terminal_module._TmuxInteractiveTerminalBackend()
        )
        self.calls: list[str] = []
        self.timeouts: list[float] = []
        self.active_calls = 0
        self.maximum_active_calls = 0

    def _invoke(
        self,
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        timeout_sec = kwargs.get("timeout_sec")
        assert isinstance(timeout_sec, float)
        self.calls.append(name)
        self.timeouts.append(timeout_sec)
        self.active_calls += 1
        self.maximum_active_calls = max(
            self.maximum_active_calls,
            self.active_calls,
        )
        try:
            operation = getattr(self._delegate, name)
            return operation(*args, **kwargs)
        finally:
            self.active_calls -= 1

    def start_server(
        self,
        socket_path: Path,
        session_name: str,
        *,
        env: dict[str, str],
        timeout_sec: float,
    ) -> None:
        self._invoke(
            "start_server",
            socket_path,
            session_name,
            env=env,
            timeout_sec=timeout_sec,
        )

    def start_pane(
        self,
        socket_path: Path,
        session_name: str,
        command: Sequence[str],
        *,
        cwd: Path | None,
        exit_status_path: Path,
        timeout_sec: float,
    ) -> str:
        value = self._invoke(
            "start_pane",
            socket_path,
            session_name,
            command,
            cwd=cwd,
            exit_status_path=exit_status_path,
            timeout_sec=timeout_sec,
        )
        assert isinstance(value, str)
        return value

    def pane_process_status(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> PaneProcessStatus:
        value = self._invoke(
            "pane_process_status",
            socket_path,
            target,
            timeout_sec=timeout_sec,
        )
        assert isinstance(value, PaneProcessStatus)
        return value

    def server_alive(
        self,
        socket_path: Path,
        session_name: str,
        *,
        timeout_sec: float,
    ) -> bool:
        value = self._invoke(
            "server_alive",
            socket_path,
            session_name,
            timeout_sec=timeout_sec,
        )
        assert isinstance(value, bool)
        return value

    def offer_literal(
        self,
        socket_path: Path,
        target: str,
        literal_text: str,
        *,
        timeout_sec: float,
    ) -> None:
        self._invoke(
            "offer_literal",
            socket_path,
            target,
            literal_text,
            timeout_sec=timeout_sec,
        )

    def offer_keys(
        self,
        socket_path: Path,
        target: str,
        keys: Sequence[str],
        *,
        timeout_sec: float,
    ) -> None:
        self._invoke(
            "offer_keys",
            socket_path,
            target,
            keys,
            timeout_sec=timeout_sec,
        )

    def close_pane(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> None:
        self._invoke(
            "close_pane",
            socket_path,
            target,
            timeout_sec=timeout_sec,
        )

    def close_server(
        self,
        socket_path: Path,
        *,
        timeout_sec: float,
    ) -> None:
        self._invoke(
            "close_server",
            socket_path,
            timeout_sec=timeout_sec,
        )


def _p2_invocation(tmp_path: Path) -> InteractiveMemberInvocation:
    support = InteractiveSessionSupport(
        schema_version="interactive_terminal_turn_queue.v1",
        turn_boundary_messages=True,
        command=("provider-client", "${PROMPT}"),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )
    return InteractiveMemberInvocation(
        invocation_id="p2-invocation",
        member_id="p2-member",
        attempt_scope_key="p2-scope",
        attempt_ordinal=1,
        resolved_command=("provider-client", "initial"),
        cwd=tmp_path,
        env=MappingProxyType({}),
        support=support,
    )


def _p2_adapter(
    tmp_path: Path,
    *,
    backend: _P2StartBackend,
    clock: _P2Clock,
) -> InteractiveTerminalTurnQueueAdapter:
    return InteractiveTerminalTurnQueueAdapter(
        tmp_path / "interactive-terminal",
        socket_root=Path(tempfile.gettempdir()),
        backend=backend,
        monotonic=clock.monotonic,
        wait=clock.wait,
        operation_timeout_sec=5.0,
    )


@pytest.mark.parametrize(
    ("mode", "deadline", "expected_allocation", "expected_cleanup"),
    (
        pytest.param(
            "success",
            100.0,
            "none",
            "not_required",
            id="no-allocation",
        ),
        pytest.param(
            "complete_failure",
            101.0,
            "possible_or_allocated",
            "completed",
            id="completed-cleanup",
        ),
        pytest.param(
            "incomplete_failure",
            101.0,
            "possible_or_allocated",
            "incomplete",
            id="incomplete-cleanup",
        ),
    ),
)
def test_phased_adapter_feasibility_failed_start_outcomes_are_closed(
    tmp_path: Path,
    mode: str,
    deadline: float,
    expected_allocation: str,
    expected_cleanup: str,
) -> None:
    clock = _P2Clock()
    backend = _P2StartBackend(mode)
    adapter = _p2_adapter(tmp_path, backend=backend, clock=clock)

    outcome = adapter.start(_p2_invocation(tmp_path), deadline=deadline)

    assert type(outcome) is InteractiveTerminalStartOutcome
    assert outcome.status == "failed"
    assert outcome.handle is None
    assert outcome.backend_allocation == expected_allocation
    assert outcome.cleanup_status == expected_cleanup
    assert not isinstance(outcome.proof, FailedCleanupProof)
    if expected_cleanup == "not_required":
        assert backend.actions == []
        assert backend.server_live is False
        assert backend.pane_live is False
        assert outcome.error_code == "start_timeout"
        assert outcome.provider_zero_survivor_proven is True
        assert type(outcome.proof) is NoBackendAllocationProof
    elif expected_cleanup == "completed":
        assert backend.actions == [
            "start_server",
            "server_alive",
            "close_server",
            "server_alive",
        ]
        assert backend.server_live is False
        assert backend.pane_live is False
        assert outcome.error_code == "server_start_failed"
        assert outcome.provider_zero_survivor_proven is True
        assert outcome.proof == PhasedFailedCleanupEvidence(
            disposition="failed_cleanup",
            pane_absent=True,
            server_absent=True,
            cleanup_complete=True,
            error_code=None,
        )
    else:
        assert backend.actions == [
            "start_server",
            "server_alive",
            "close_server",
            "server_alive",
        ]
        assert backend.server_live is True
        assert backend.pane_live is False
        assert (
            outcome.error_code
            == "interactive_terminal_start_cleanup_incomplete"
        )
        assert outcome.provider_zero_survivor_proven is False
        assert type(outcome.proof) is PhasedFailedCleanupEvidence
        assert outcome.proof == PhasedFailedCleanupEvidence(
            disposition="failed_cleanup",
            pane_absent=False,
            server_absent=False,
            cleanup_complete=False,
            error_code="interactive_terminal_start_cleanup_incomplete",
        )


def test_phased_adapter_feasibility_post_start_cleanup_stays_handle_bound(
    tmp_path: Path,
) -> None:
    clock = _P2Clock()
    backend = _P2StartBackend("success")
    adapter = _p2_adapter(tmp_path, backend=backend, clock=clock)
    outcome = adapter.start(
        _p2_invocation(tmp_path),
        deadline=clock.value + 1.0,
    )
    assert outcome.status == "started"
    handle = outcome.handle
    assert handle is not None

    proof = adapter.abort(handle, deadline=clock.value + 1.0)

    assert proof == FailedCleanupProof(
        disposition="failed_cleanup",
        handle_id=handle.handle_id,
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )
    assert backend.actions == [
        "start_server",
        "start_pane",
        "server_alive",
        "pane_process_status",
        "pane_process_status",
        "close_pane",
        "pane_process_status",
        "server_alive",
        "close_server",
        "server_alive",
    ]
    assert backend.server_live is False
    assert backend.pane_live is False
    assert project_phased_failed_cleanup_evidence(
        proof,
        active_handle_id="",
    ) is None
    assert project_phased_failed_cleanup_evidence(
        proof,
        active_handle_id="different-handle",
    ) is None
    projected = project_phased_failed_cleanup_evidence(
        proof,
        active_handle_id=handle.handle_id,
    )
    assert projected == PhasedFailedCleanupEvidence(
        disposition="failed_cleanup",
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )
    assert not hasattr(projected, "handle_id")


def _fixture_path() -> Path:
    return (
        Path(__file__).parents[1]
        / "fixtures"
        / "workflow_lisp"
        / "provider_peer_group"
        / "real_adapter_prompt.md"
    )


def _marker_command(
    *,
    marker_env: str,
    release_env: str,
    marker_value: str,
    write_bundle: bool = False,
) -> str:
    source_lines = [
        "import os",
        "import time",
        "from pathlib import Path",
        f"marker = Path(os.environ[{marker_env!r}])",
        f"release = Path(os.environ[{release_env!r}])",
    ]
    if write_bundle:
        source_lines.extend(
            (
                "bundle = Path("
                "os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH']"
                ")",
                "bundle.write_text("
                f"{json.dumps(_EXPECTED_VALUE)!r}, encoding='utf-8'"
                ")",
            )
        )
    source_lines.extend(
        (
            "previous = ("
            "marker.read_text(encoding='utf-8') "
            "if marker.exists() else ''"
            ")",
            "temporary = marker.with_name(marker.name + '.tmp')",
            "temporary.write_text("
            f"previous + {marker_value + chr(10)!r}, encoding='utf-8'"
            ")",
            "temporary.replace(marker)",
        )
    )
    source_lines.extend(
        (
            "while not release.exists():",
            "    time.sleep(0.05)",
        )
    )
    return " ".join(
        (
            shlex.quote(sys.executable),
            "-c",
            shlex.quote("\n".join(source_lines)),
        )
    )


def _render_prompt(task_action_command: str) -> str:
    rendered = "\n".join(
        (
            "This is a bounded two-turn delivery check launched from a trusted "
            "checkout. Treat the checkout as read-only. The only permitted "
            "mutations are the declared temporary marker, release, and output "
            "bundle paths.",
            "",
            "Perform exactly one task action in this initial turn by using the "
            "shell to run exactly:",
            f"`{task_action_command}`",
            "The command waits until the harness releases it. After it "
            "succeeds, end the initial turn naturally and wait for a literal "
            "queued message. Do not write the output bundle.",
            "",
            "For each later literal queued message, run only the exact command "
            "that the message supplies, wait for it to succeed, then end that "
            "turn naturally. Never use an orchestrator peer command, "
            "interruption, cancellation, resume, directives, peer-send, raw "
            "pane inspection, or a client close command.",
            "",
        )
    )
    return rendered


def _render_literal_offer(
    *,
    message_id: str,
    command: str,
    final_offer: bool,
) -> str:
    final_instruction = (
        "The command writes the output bundle. After it succeeds, end this "
        "turn naturally and invoke no more tools."
        if final_offer
        else (
            "After it succeeds, end this turn naturally and wait for the next "
            "literal queued message."
        )
    )
    return "\n".join(
        (
            "ORCHESTRATOR_ADAPTER_LITERAL_OFFER_V1",
            f"message_id: {message_id}",
            "",
            "Use the shell to run exactly:",
            f"`{command}`",
            final_instruction,
            "",
        )
    )


def _wait_for_marker(
    path: Path,
    *,
    expected: str,
    deadline: float,
) -> None:
    while time.monotonic() < deadline:
        if path.is_file():
            observed = path.read_text(encoding="utf-8")
            if observed == expected:
                return
            pytest.fail(
                f"unexpected marker content for {path.name}: {observed!r}"
            )
        time.sleep(0.05)
    pytest.fail(f"timed out waiting for marker: {path.name}")


def _render_role_prompt(role: str, *, sync_marker: Path) -> str:
    fixture_name = _ROLE_PROMPT_FIXTURES[role]
    template_path = _fixture_path().with_name(fixture_name)
    assert template_path.is_file(), (
        f"{role} prompt fixture is missing"
    )
    rendered = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{PYTHON}}": shlex.quote(sys.executable),
        "{{MESSAGE_JSON}}": json.dumps(
            _COORDINATOR_MESSAGE,
            ensure_ascii=False,
        ),
        "{{MESSAGE_SHELL}}": shlex.quote(_COORDINATOR_MESSAGE),
        "{{SENDER_VALUE_JSON}}": json.dumps(
            _COORDINATOR_SENDER_VALUE,
        ),
        "{{SYNC_MARKER_SHELL}}": shlex.quote(str(sync_marker)),
    }
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    assert "{{" not in rendered and "}}" not in rendered
    return rendered


def _write_coordinator_fixture(
    workspace: Path,
    *,
    sync_marker: Path,
) -> dict[str, Path]:
    files = {
        "source": workspace / "real_peer_delivery.orc",
        "providers": workspace / "providers.json",
        "prompts": workspace / "prompts.json",
        "sender": workspace / "sender.md",
        "receiver": workspace / "receiver.md",
    }
    files["source"].write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.17")',
                "  (defmodule real_peer_delivery)",
                "  (export orchestrate)",
                "  (defrecord DeliveryResult",
                "    (sender String)",
                "    (receiver String))",
                "  (defworkflow orchestrate () -> DeliveryResult",
                "    (with-live-provider-peers",
                "      ((sender",
                "         (provider-result providers.sender",
                "           :prompt prompts.sender",
                "           :inputs ()",
                "           :timeout-sec 300",
                "           :returns String))",
                "       (receiver",
                "         (provider-result providers.receiver",
                "           :prompt prompts.receiver",
                "           :inputs ()",
                "           :timeout-sec 300",
                "           :returns String)))",
                "      (record DeliveryResult",
                "        :sender sender",
                "        :receiver receiver))))",
                "",
            )
        ),
        encoding="utf-8",
    )
    files["providers"].write_text(
        json.dumps(
            {
                "providers.receiver": "codex",
                "providers.sender": "codex",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["prompts"].write_text(
        json.dumps(
            {
                "prompts.receiver": "receiver.md",
                "prompts.sender": "sender.md",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files["sender"].write_text(
        _render_role_prompt("sender", sync_marker=sync_marker),
        encoding="utf-8",
    )
    files["receiver"].write_text(
        _render_role_prompt("receiver", sync_marker=sync_marker),
        encoding="utf-8",
    )
    return files


def _write_three_member_fixture(
    workspace: Path,
    *,
    sync_marker: Path,
) -> dict[str, Path]:
    fixture_root = _fixture_path().parent
    files: dict[str, Path] = {}
    for key, filename in _THREE_MEMBER_FIXTURES.items():
        destination = workspace / filename
        destination.write_bytes((fixture_root / filename).read_bytes())
        files[key] = destination

    replacements = {
        "{{PYTHON}}": shlex.quote(sys.executable),
        "{{MESSAGE_SHELL}}": shlex.quote(_COORDINATOR_MESSAGE),
        "{{SYNC_MARKER_SHELL}}": shlex.quote(str(sync_marker)),
    }
    for role, filename in _THREE_MEMBER_ROLE_PROMPTS.items():
        rendered = (fixture_root / filename).read_text(encoding="utf-8")
        for marker, value in replacements.items():
            rendered = rendered.replace(marker, value)
        assert "{{" not in rendered and "}}" not in rendered
        destination = workspace / filename
        destination.write_text(rendered, encoding="utf-8")
        files[role] = destination
    return files


def _coordinator_build_request(
    workspace: Path,
    files: dict[str, Path],
) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["source"],
        source_roots=(workspace,),
        entry_workflow="orchestrate",
        provider_externs_path=files["providers"],
        prompt_externs_path=files["prompts"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=workspace,
    )


def _coordinator_run_args(
    files: dict[str, Path],
    *,
    state_dir: Path,
) -> Namespace:
    return Namespace(
        workflow=str(files["source"]),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=str(state_dir),
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        quiet=True,
        verbose=False,
        log_level="error",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="orchestrate",
        source_root=[str(files["source"].parent)],
        provider_externs_file=str(files["providers"]),
        prompt_externs_file=str(files["prompts"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def _peer_socket_paths() -> set[Path]:
    roots = [Path(tempfile.gettempdir())]
    if os.name == "posix" and Path("/tmp") not in roots:
        roots.append(Path("/tmp"))
    return {
        path
        for root in roots
        if root.is_dir()
        for pattern in (
            "orchestrator-peer-*.sock",
            "orc-peer-*.sock",
        )
        for path in root.glob(pattern)
    }


def test_peer_socket_snapshot_covers_endpoint_and_adapter_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    endpoint = tmp_path / "orchestrator-peer-endpoint.sock"
    adapter = tmp_path / "orc-peer-adapter.sock"
    unrelated = tmp_path / "other.sock"
    for path in (endpoint, adapter, unrelated):
        path.touch()

    snapshot = _peer_socket_paths()

    assert endpoint in snapshot
    assert adapter in snapshot
    assert unrelated not in snapshot


def _receive(
    listener: PeerProtocolListener,
    request_type: type,
) -> PeerProtocolEvent:
    event = listener.receive_event(timeout_sec=_EVENT_TIMEOUT_SEC)
    assert isinstance(event.request, request_type)
    return event


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@pytest.mark.e2e
def test_real_adapter_phased_adapter_feasibility_two_successive_offers(
    tmp_path: Path,
) -> None:
    """Deliver two natural-boundary turns through one production client."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    workspace = tmp_path / "provider-peer-real-adapter"
    workspace.mkdir()
    trusted_checkout = Path(
        os.environ.get(
            "ORCHESTRATE_E2E_TRUSTED_CHECKOUT",
            str(_REPO_ROOT),
        )
    ).resolve()
    assert trusted_checkout.is_dir()
    receiver_attempt = PeerAttemptIdentity(
        member_id="receiver",
        attempt_scope_key="real-adapter-receiver-scope",
        attempt_ordinal=1,
    )
    runtime_root = workspace / ".orchestrate" / "provider-peer-real"
    transport_temp = tempfile.TemporaryDirectory(prefix="orc-peer-e2e-")
    transport_root = Path(transport_temp.name)
    bundle_path = runtime_root / "member-result.json"
    task_action_marker = runtime_root / "task-action.marker"
    task_action_release = runtime_root / "task-action.release"
    first_offer_marker = runtime_root / "first-offer.marker"
    first_offer_release = runtime_root / "first-offer.release"
    second_offer_marker = runtime_root / "second-offer.marker"
    second_offer_release = runtime_root / "second-offer.release"
    runtime_root.mkdir(parents=True)
    task_action_command = _marker_command(
        marker_env=_TASK_ACTION_MARKER_ENV,
        release_env=_TASK_ACTION_RELEASE_ENV,
        marker_value="counted-task-action-1",
    )
    first_offer_command = _marker_command(
        marker_env=_FIRST_OFFER_MARKER_ENV,
        release_env=_FIRST_OFFER_RELEASE_ENV,
        marker_value=_MESSAGE_ID,
    )
    second_offer_command = _marker_command(
        marker_env=_SECOND_OFFER_MARKER_ENV,
        release_env=_SECOND_OFFER_RELEASE_ENV,
        marker_value=_SECOND_MESSAGE_ID,
        write_bundle=True,
    )
    prompt = _render_prompt(task_action_command)
    first_literal_offer = _render_literal_offer(
        message_id=_MESSAGE_ID,
        command=first_offer_command,
        final_offer=False,
    )
    second_literal_offer = _render_literal_offer(
        message_id=_SECOND_MESSAGE_ID,
        command=second_offer_command,
        final_offer=True,
    )
    registry = ProviderRegistry()
    provider = registry.get("codex")
    assert provider is not None
    assert provider.interactive_session_support is not None
    executor = ProviderExecutor(workspace, registry)
    configured_operation_timeout = _EVENT_TIMEOUT_SEC * 2
    production_backend = _RecordingProductionBackend()
    adapter = InteractiveTerminalTurnQueueAdapter(
        transport_root / "interactive-terminal",
        backend=production_backend,
        operation_timeout_sec=configured_operation_timeout,
    )
    attempt_deadline = time.monotonic() + _EVENT_TIMEOUT_SEC
    handle: InteractiveMemberHandle | None = None
    natural_proof: NaturalShutdownProof | None = None

    try:
        inherited_python_path = os.environ.get("PYTHONPATH")
        python_path = str(_REPO_ROOT)
        if inherited_python_path:
            python_path = os.pathsep.join(
                (python_path, inherited_python_path)
            )
        # Interactive Codex has an exact-project trust chooser for new
        # temporary roots. Launch from the already trusted checkout so that
        # the adapter exercises only declared provider turns; every mutable
        # marker, release, bundle, and tmux artifact remains under tmp_path.
        invocation, error = executor.prepare_interactive_invocation(
            provider_name="codex",
            params={},
            context={},
            prompt_content=prompt,
            invocation_id="real-adapter-invocation",
            member_id=receiver_attempt.member_id,
            attempt_scope_key=receiver_attempt.attempt_scope_key,
            attempt_ordinal=receiver_attempt.attempt_ordinal,
            cwd=trusted_checkout,
            env={
                "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle_path),
                "PYTHONPATH": python_path,
                _TASK_ACTION_MARKER_ENV: str(task_action_marker),
                _TASK_ACTION_RELEASE_ENV: str(task_action_release),
                _FIRST_OFFER_MARKER_ENV: str(first_offer_marker),
                _FIRST_OFFER_RELEASE_ENV: str(first_offer_release),
                _SECOND_OFFER_MARKER_ENV: str(second_offer_marker),
                _SECOND_OFFER_RELEASE_ENV: str(second_offer_release),
            },
        )
        assert error is None
        assert invocation is not None
        assert invocation.support is provider.interactive_session_support
        assert "resume" not in invocation.resolved_command[:-1]
        assert "--ephemeral" not in invocation.resolved_command[:-1]

        start_outcome = adapter.start(
            invocation,
            deadline=attempt_deadline,
        )
        assert start_outcome.status == "started"
        assert start_outcome.handle is not None
        handle = start_outcome.handle
        _wait_for_marker(
            task_action_marker,
            expected="counted-task-action-1\n",
            deadline=attempt_deadline,
        )

        first_offer_receipt = adapter.offer(
            handle,
            first_literal_offer,
            deadline=attempt_deadline,
        )
        assert first_offer_receipt.status == "offered"
        assert first_offer_receipt.handle_id == handle.handle_id
        assert first_offer_receipt.byte_count == len(
            first_literal_offer.encode("utf-8")
        )
        assert first_offer_receipt.content_sha256 == _sha256(
            first_literal_offer.encode("utf-8")
        )
        task_action_release.touch()
        _wait_for_marker(
            first_offer_marker,
            expected=f"{_MESSAGE_ID}\n",
            deadline=attempt_deadline,
        )

        second_offer_receipt = adapter.offer(
            handle,
            second_literal_offer,
            deadline=attempt_deadline,
        )
        assert second_offer_receipt.status == "offered"
        assert second_offer_receipt.handle_id == handle.handle_id
        assert second_offer_receipt.byte_count == len(
            second_literal_offer.encode("utf-8")
        )
        assert second_offer_receipt.content_sha256 == _sha256(
            second_literal_offer.encode("utf-8")
        )
        first_offer_release.touch()
        _wait_for_marker(
            second_offer_marker,
            expected=f"{_SECOND_MESSAGE_ID}\n",
            deadline=attempt_deadline,
        )

        artifacts = validate_output_bundle(
            {
                "path": bundle_path.relative_to(workspace).as_posix(),
                "fields": [
                    {
                        "name": "__result__",
                        "json_pointer": "",
                        "type": "string",
                        "required": True,
                    }
                ],
            },
            workspace=workspace,
        )
        assert artifacts == {"__result__": _EXPECTED_VALUE}
        exact_bundle_bytes = bundle_path.read_bytes()
        bundle_value = json.loads(exact_bundle_bytes.decode("utf-8"))
        assert bundle_value == _EXPECTED_VALUE
        assert bundle_path.read_bytes() == exact_bundle_bytes
        frozen = FrozenPeerMemberResult.create(
            attempt=receiver_attempt,
            exact_bundle_bytes=exact_bundle_bytes,
            value=bundle_value,
        )
        assert frozen.value == _EXPECTED_VALUE
        assert frozen.exact_bundle_bytes == exact_bundle_bytes
        assert frozen.bundle_sha256 == _sha256(exact_bundle_bytes)

        close_receipt = adapter.offer_close(
            handle,
            deadline=attempt_deadline,
        )
        assert close_receipt.status == "close_offered"
        second_offer_release.touch()
        natural_proof = adapter.join(
            handle,
            deadline=attempt_deadline,
        )
        assert natural_proof == NaturalShutdownProof(
            disposition="natural_exit",
            handle_id=handle.handle_id,
            return_code=0,
            pane_absent=True,
            server_absent=True,
            proof_complete=True,
        )
        for forcing_surface in (
            "cancel_and_reap",
            "resume",
            "steer",
            "directive",
        ):
            assert not hasattr(adapter, forcing_surface)
        assert production_backend.calls.count("start_server") == 1
        assert production_backend.calls.count("start_pane") == 1
        assert production_backend.calls.count("offer_literal") == 3
        assert production_backend.calls.count("offer_keys") == 6
        assert production_backend.active_calls == 0
        assert production_backend.maximum_active_calls == 1
        assert production_backend.timeouts
        assert all(
            0.0 < timeout < configured_operation_timeout
            for timeout in production_backend.timeouts
        )
        assert task_action_marker.read_text(
            encoding="utf-8"
        ).splitlines() == ["counted-task-action-1"]
        assert first_offer_marker.read_text(
            encoding="utf-8"
        ).splitlines() == [_MESSAGE_ID]
        assert second_offer_marker.read_text(
            encoding="utf-8"
        ).splitlines() == [_SECOND_MESSAGE_ID]
        assert not handle.socket_path.exists()
    finally:
        try:
            if handle is not None and natural_proof is None:
                cleanup_proof = adapter.abort(
                    handle,
                    deadline=time.monotonic() + 30.0,
                )
                assert cleanup_proof == FailedCleanupProof(
                    disposition="failed_cleanup",
                    handle_id=handle.handle_id,
                    pane_absent=True,
                    server_absent=True,
                    cleanup_complete=True,
                    error_code=None,
                )
                assert production_backend.active_calls == 0
                assert not handle.socket_path.exists()
        finally:
            transport_temp.cleanup()
            assert not transport_root.exists()


@pytest.mark.e2e
def test_real_two_member_coordinator_records_peer_send_and_settles_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the production coordinator through one natural peer exchange."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    fixture_root = tmp_path / "provider-peer-real-coordinator"
    fixture_root.mkdir()
    state_dir = tmp_path / "provider-peer-real-runs"
    sync_marker = (
        tmp_path
        / "provider-peer-turn-boundary"
        / "peer-send-succeeded"
    )
    sync_marker.parent.mkdir()
    assert not sync_marker.exists()
    files = _write_coordinator_fixture(
        fixture_root,
        sync_marker=sync_marker,
    )
    built = build_frontend_bundle(
        _coordinator_build_request(fixture_root, files)
    )
    [node] = built.validated_bundle.ir.nodes.values()
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    config = node.execution_config
    assert tuple(
        member.member_id for member in config.members
    ) == ("sender", "receiver")

    inherited_python_path = os.environ.get("PYTHONPATH")
    python_path = str(_REPO_ROOT)
    if inherited_python_path:
        python_path = os.pathsep.join(
            (python_path, inherited_python_path)
        )
    monkeypatch.setenv("PYTHONPATH", python_path)
    monkeypatch.chdir(_REPO_ROOT)
    sockets_before = _peer_socket_paths()

    assert run_workflow(
        _coordinator_run_args(files, state_dir=state_dir)
    ) == 0

    assert sync_marker.is_file()
    assert _peer_socket_paths() == sockets_before
    [run_root] = state_dir.iterdir()
    state = json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )
    expected_settlement = {
        "sender": _COORDINATOR_SENDER_VALUE,
        "receiver": _COORDINATOR_MESSAGE,
    }
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        "return__sender": _COORDINATOR_SENDER_VALUE,
        "return__receiver": _COORDINATOR_MESSAGE,
    }
    assert len(state["provider_attempt_allocations"]) == 2
    [step] = state["steps"].values()
    assert step["status"] == "completed"
    assert step["artifacts"] == expected_settlement

    terminal_path = (
        run_root
        / step["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    terminal = PeerGroupTerminalEvidence.from_dict(
        json.loads(terminal_path.read_text(encoding="ascii"))
    )
    assert terminal.outcome == "completed"
    assert terminal.failure is None
    assert (
        terminal.endpoint_drained,
        terminal.endpoint_closed,
        terminal.endpoint_workers_joined,
    ) == (True, True, True)
    assert terminal.settlement_sha256 == _sha256(
        canonical_json_for_pure_value(expected_settlement).encode("utf-8")
    )
    assert tuple(
        member.attempt.member_id for member in terminal.members
    ) == ("sender", "receiver")

    realized = realize_provider_peer_group_paths(
        run_root=run_root,
        plan=config.paths,
        visit_count=terminal.group_visit.visit_count,
        attempt_ordinals={
            member.attempt.member_id: member.attempt.attempt_ordinal
            for member in terminal.members
        },
    )
    assert realized.terminal_evidence_path == terminal_path
    terminal_by_member = {
        member.attempt.member_id: member
        for member in terminal.members
    }
    realized_by_member = {
        member.member_id: member for member in realized.members
    }
    expected_values = {
        "sender": _COORDINATOR_SENDER_VALUE,
        "receiver": _COORDINATOR_MESSAGE,
    }
    for member_id, value in expected_values.items():
        paths = realized_by_member[member_id]
        evidence = terminal_by_member[member_id]
        expected_bytes = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        assert paths.provisional_bundle_path.read_bytes() == expected_bytes
        frozen = FrozenPeerMemberResult.create(
            attempt=evidence.attempt,
            exact_bundle_bytes=expected_bytes,
            value=value,
        )
        assert frozen.bundle_sha256 == evidence.frozen_bundle_sha256
        assert json.loads(
            paths.evidence_path.read_text(encoding="ascii")
        ) == evidence.to_dict()
        assert evidence.natural_shutdown is not None
        assert evidence.natural_shutdown.to_dict() == {
            "disposition": "natural_exit",
            "return_code": 0,
            "pane_absent": True,
            "server_absent": True,
            "proof_complete": True,
        }
        assert evidence.failed_cleanup is None

    sender_paths = realized_by_member["sender"]
    sender_summary = inspect_peer_message_ledger(
        sender_paths.injected_messages_path
    )
    assert sender_summary == terminal_by_member["sender"].ledger
    assert sender_summary.row_count == 1
    assert sender_summary.counts.to_dict() == {
        "recorded": 0,
        "offered": 0,
        "offer_failed": 0,
        "receiver_acknowledged": 0,
    }
    sender_rows = tuple(
        json.loads(line)
        for line in sender_paths.injected_messages_path.read_text(
            encoding="ascii"
        ).splitlines()
    )
    assert tuple(row["row_kind"] for row in sender_rows) == ("header",)
    assert sender_rows[0]["group_visit"] == terminal.group_visit.to_dict()
    assert sender_rows[0]["receiver_attempt"] == (
        terminal_by_member["sender"].attempt.to_dict()
    )

    receiver_paths = realized_by_member["receiver"]
    receiver_summary = inspect_peer_message_ledger(
        receiver_paths.injected_messages_path
    )
    assert receiver_summary == terminal_by_member["receiver"].ledger
    assert receiver_summary.row_count == 4
    assert receiver_summary.counts.to_dict() == {
        "recorded": 1,
        "offered": 1,
        "offer_failed": 0,
        "receiver_acknowledged": 1,
    }
    receiver_rows = tuple(
        json.loads(line)
        for line in receiver_paths.injected_messages_path.read_text(
            encoding="ascii"
        ).splitlines()
    )
    assert tuple(row["row_kind"] for row in receiver_rows) == (
        "header",
        "recorded",
        "offered",
        "receiver_acknowledged",
    )
    header, recorded, offered, acknowledged = receiver_rows
    receiver_attempt = terminal_by_member["receiver"].attempt.to_dict()
    sender_attempt = terminal_by_member["sender"].attempt.to_dict()
    assert header["group_visit"] == terminal.group_visit.to_dict()
    assert header["receiver_attempt"] == receiver_attempt
    assert recorded["coordinator_sequence"] == 1
    assert recorded["sender_attempt"] == sender_attempt
    assert recorded["receiver_attempt"] == receiver_attempt
    assert recorded["content"] == _COORDINATOR_MESSAGE
    assert recorded["content_sha256"] == _sha256(
        _COORDINATOR_MESSAGE.encode("utf-8")
    )
    assert offered["message_id"] == recorded["message_id"]
    assert offered["receiver_attempt"] == receiver_attempt
    assert offered["byte_count"] == len(
        _COORDINATOR_MESSAGE.encode("utf-8")
    )
    assert offered["content_sha256"] == recorded["content_sha256"]
    assert acknowledged["message_id"] == recorded["message_id"]
    assert acknowledged["receiver_attempt"] == receiver_attempt
    assert not list(run_root.rglob("*.sock"))


@pytest.mark.e2e
def test_real_three_member_workflow_runs_through_public_surface(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Compile and run a three-member peer group through the public surface."""

    skip_if_no_e2e()
    for executable in ("codex", "git", "tmux"):
        skip_if_no_cli(executable)

    fixture_root = tmp_path / "provider-peer-real-three"
    fixture_root.mkdir()
    state_dir = tmp_path / "provider-peer-real-three-runs"
    sync_marker = tmp_path / "provider-peer-real-three-sync" / "sent"
    sync_marker.parent.mkdir()
    assert not sync_marker.exists()
    files = _write_three_member_fixture(
        fixture_root,
        sync_marker=sync_marker,
    )
    built = build_frontend_bundle(
        _coordinator_build_request(fixture_root, files)
    )
    [node] = built.validated_bundle.ir.nodes.values()
    assert node.kind is ExecutableNodeKind.PROVIDER_PEER_GROUP
    config = node.execution_config
    assert tuple(member.member_id for member in config.members) == (
        "sender",
        "receiver",
        "witness",
    )

    inherited_python_path = os.environ.get("PYTHONPATH")
    python_path = str(_REPO_ROOT)
    if inherited_python_path:
        python_path = os.pathsep.join(
            (python_path, inherited_python_path)
        )
    monkeypatch.setenv("PYTHONPATH", python_path)
    monkeypatch.chdir(_REPO_ROOT)
    sockets_before = _peer_socket_paths()

    assert run_workflow(
        _coordinator_run_args(files, state_dir=state_dir)
    ) == 0

    assert sync_marker.is_file()
    assert _peer_socket_paths() == sockets_before
    [run_root] = state_dir.iterdir()
    state = json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )
    expected_settlement = {
        "sender": "sender-complete",
        "received": _COORDINATOR_MESSAGE,
        "witness": True,
    }
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {
        f"return__{name}": value
        for name, value in expected_settlement.items()
    }
    assert len(state["provider_attempt_allocations"]) == 3
    [step] = state["steps"].values()
    assert step["status"] == "completed"
    assert step["artifacts"] == expected_settlement

    terminal_path = (
        run_root
        / step["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    terminal = PeerGroupTerminalEvidence.from_dict(
        json.loads(terminal_path.read_text(encoding="ascii"))
    )
    assert terminal.outcome == "completed"
    assert terminal.failure is None
    assert tuple(
        member.attempt.member_id for member in terminal.members
    ) == ("sender", "receiver", "witness")
    assert (
        terminal.endpoint_drained,
        terminal.endpoint_closed,
        terminal.endpoint_workers_joined,
    ) == (True, True, True)
    assert terminal.settlement_sha256 == _sha256(
        canonical_json_for_pure_value(expected_settlement).encode("utf-8")
    )
    assert all(
        member.natural_shutdown is not None
        and member.natural_shutdown.return_code == 0
        and member.natural_shutdown.pane_absent
        and member.natural_shutdown.server_absent
        and member.natural_shutdown.proof_complete
        and member.failed_cleanup is None
        for member in terminal.members
    )

    realized = realize_provider_peer_group_paths(
        run_root=run_root,
        plan=config.paths,
        visit_count=terminal.group_visit.visit_count,
        attempt_ordinals={
            member.attempt.member_id: member.attempt.attempt_ordinal
            for member in terminal.members
        },
    )
    terminal_by_member = {
        member.attempt.member_id: member
        for member in terminal.members
    }
    realized_by_member = {
        member.member_id: member for member in realized.members
    }
    expected_values = {
        "sender": "sender-complete",
        "receiver": _COORDINATOR_MESSAGE,
        "witness": True,
    }
    for member_id, value in expected_values.items():
        paths = realized_by_member[member_id]
        evidence = terminal_by_member[member_id]
        exact_bytes = json.dumps(
            value,
            ensure_ascii=False,
        ).encode("utf-8")
        assert paths.provisional_bundle_path.read_bytes() == exact_bytes
        assert evidence.frozen_bundle_sha256 == _sha256(exact_bytes)
        assert json.loads(
            paths.evidence_path.read_text(encoding="ascii")
        ) == evidence.to_dict()

    for member_id in ("sender", "witness"):
        paths = realized_by_member[member_id]
        rows = tuple(
            json.loads(line)
            for line in paths.injected_messages_path.read_text(
                encoding="ascii"
            ).splitlines()
        )
        assert tuple(row["row_kind"] for row in rows) == ("header",)
        assert inspect_peer_message_ledger(
            paths.injected_messages_path
        ) == terminal_by_member[member_id].ledger

    receiver_paths = realized_by_member["receiver"]
    receiver_rows = tuple(
        json.loads(line)
        for line in receiver_paths.injected_messages_path.read_text(
            encoding="ascii"
        ).splitlines()
    )
    assert tuple(row["row_kind"] for row in receiver_rows) == (
        "header",
        "recorded",
        "offered",
        "receiver_acknowledged",
    )
    _, recorded, offered, acknowledged = receiver_rows
    assert recorded["sender_attempt"] == (
        terminal_by_member["sender"].attempt.to_dict()
    )
    assert recorded["receiver_attempt"] == (
        terminal_by_member["receiver"].attempt.to_dict()
    )
    assert recorded["content"] == _COORDINATOR_MESSAGE
    assert offered["message_id"] == recorded["message_id"]
    assert acknowledged["message_id"] == recorded["message_id"]
    assert inspect_peer_message_ledger(
        receiver_paths.injected_messages_path
    ) == terminal_by_member["receiver"].ledger
    assert not list(run_root.rglob("*.sock"))

    capsys.readouterr()
    assert report_workflow(
        run_id=run_root.name,
        runs_root=str(state_dir),
        format="json",
    ) == 0
    report = json.loads(capsys.readouterr().out)
    [reported_step] = report["steps"]
    assert reported_step["kind"] == "provider_peer_group"
    assert (
        reported_step["output"]["debug"]["provider_peer_group"]
        == step["debug"]["provider_peer_group"]
    )
