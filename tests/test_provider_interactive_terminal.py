"""Structural provider capability tests for interactive terminal sessions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import subprocess
from types import MappingProxyType
from typing import Sequence

import orchestrator.providers as provider_api
from orchestrator.providers import interactive_terminal as interactive_terminal_module
import pytest

from orchestrator.providers import (
    CallPolicyBinding,
    InputMode,
    InteractiveSessionSupport,
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionSupport,
    ProviderTemplate,
)
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    WorkflowMappingValidationResult,
    validate_workflow_mapping,
)
from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalError,
    InteractiveTerminalTurnQueueAdapter,
    NaturalShutdownProof,
    OfferReceipt,
    PaneProcessStatus,
)


SCHEMA_VERSION = "interactive_terminal_turn_queue.v1"
CAPABILITY_FIELDS = {
    "schema_version",
    "turn_boundary_messages",
    "command",
    "message_submit_keys",
    "graceful_close_text",
    "graceful_close_submit_keys",
}


def _support(**overrides: object) -> InteractiveSessionSupport:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "turn_boundary_messages": True,
        "command": ("codex", "${PROMPT}"),
        "message_submit_keys": ("ENTER",),
        "graceful_close_text": "/exit",
        "graceful_close_submit_keys": ("ENTER",),
    }
    values.update(overrides)
    return InteractiveSessionSupport(**values)  # type: ignore[arg-type]


def _provider(
    support: object,
    *,
    name: str = "peer-provider",
) -> ProviderTemplate:
    return ProviderTemplate(
        name=name,
        command=["tool", "${PROMPT}"],
        input_mode=InputMode.ARGV,
        interactive_session_support=support,  # type: ignore[arg-type]
    )


def _capability_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "turn_boundary_messages": True,
        "command": ["codex", "${PROMPT}"],
        "message_submit_keys": ["ENTER"],
        "graceful_close_text": "/exit",
        "graceful_close_submit_keys": ["ENTER"],
    }
    config.update(overrides)
    return config


def test_interactive_session_support_is_public_provider_api() -> None:
    assert hasattr(provider_api, "InteractiveSessionSupport")
    assert "InteractiveSessionSupport" in provider_api.__all__


def test_interactive_session_support_is_deeply_immutable() -> None:
    command = ["codex", "${PROMPT}"]
    message_keys = ["ENTER", "TAB"]
    close_keys = ["ENTER"]

    support = _support(
        command=command,
        message_submit_keys=message_keys,
        graceful_close_submit_keys=close_keys,
    )
    command.append("--mutated")
    message_keys.append("ESCAPE")
    close_keys.clear()

    assert support.command == ("codex", "${PROMPT}")
    assert support.message_submit_keys == ("ENTER", "TAB")
    assert support.graceful_close_submit_keys == ("ENTER",)
    with pytest.raises(FrozenInstanceError):
        support.graceful_close_text = "quit"  # type: ignore[misc]


def test_explicit_interactive_session_support_validates_structurally() -> None:
    provider = _provider(_support(message_submit_keys=("ENTER", "TAB")))

    assert provider.validate() == []
    assert provider.interactive_session_support == _support(
        message_submit_keys=("ENTER", "TAB")
    )


def test_interactive_command_participates_in_call_policy_validation() -> None:
    provider = ProviderTemplate(
        name="policy-peer",
        command=["tool", "${model}", "${PROMPT}"],
        input_mode=InputMode.ARGV,
        call_policy_bindings={
            "model": CallPolicyBinding(target_param="model"),
        },
        interactive_session_support=_support(),
    )

    errors = provider.validate()

    assert any(
        "interactive_session_support.command" in error
        and "${model}" in error
        and "exactly one" in error
        for error in errors
    ), errors


@pytest.mark.parametrize(
    ("overrides", "expected_fragments"),
    (
        pytest.param(
            {"schema_version": ""},
            ("schema_version", SCHEMA_VERSION),
            id="empty-schema",
        ),
        pytest.param(
            {"schema_version": "interactive_terminal_turn_queue.v2"},
            ("schema_version", SCHEMA_VERSION),
            id="unknown-schema",
        ),
        pytest.param(
            {"turn_boundary_messages": "true"},
            ("turn_boundary_messages", "boolean"),
            id="string-enablement",
        ),
        pytest.param(
            {"turn_boundary_messages": 1},
            ("turn_boundary_messages", "boolean"),
            id="integer-enablement",
        ),
        pytest.param(
            {"turn_boundary_messages": False},
            ("turn_boundary_messages", "true"),
            id="disabled-capability",
        ),
        pytest.param(
            {"command": ()},
            ("command", "non-empty"),
            id="empty-command",
        ),
        pytest.param(
            {"command": ("codex", "")},
            ("command", "non-empty strings"),
            id="empty-command-token",
        ),
        pytest.param(
            {"command": ("codex", "   ")},
            ("command", "non-empty strings"),
            id="blank-command-token",
        ),
        pytest.param(
            {"command": ("codex",)},
            ("command", "exactly one", "${PROMPT}"),
            id="missing-prompt",
        ),
        pytest.param(
            {"command": ("codex", "$${PROMPT}")},
            ("command", "exactly one", "${PROMPT}"),
            id="escaped-prompt-is-not-binding",
        ),
        pytest.param(
            {"command": ("codex", "${PROMPT}", "${PROMPT}")},
            ("command", "exactly one", "${PROMPT}"),
            id="duplicate-prompt",
        ),
        pytest.param(
            {"command": ("codex", "${PROMPT}", "${SESSION_ID}")},
            ("command", "must not contain", "${SESSION_ID}"),
            id="session-placeholder",
        ),
        pytest.param(
            {"message_submit_keys": ()},
            ("message_submit_keys", "non-empty"),
            id="empty-message-submit",
        ),
        pytest.param(
            {"message_submit_keys": ("",)},
            ("message_submit_keys", "non-empty strings"),
            id="empty-message-submit-token",
        ),
        pytest.param(
            {"message_submit_keys": ("SPACE",)},
            ("message_submit_keys", "unsupported key", "SPACE"),
            id="unknown-message-submit-key",
        ),
        pytest.param(
            {"graceful_close_text": ""},
            ("graceful_close_text", "non-empty"),
            id="empty-close-text",
        ),
        pytest.param(
            {"graceful_close_text": "   "},
            ("graceful_close_text", "non-empty"),
            id="blank-close-text",
        ),
        pytest.param(
            {"graceful_close_submit_keys": ()},
            ("graceful_close_submit_keys", "non-empty"),
            id="empty-close-submit",
        ),
        pytest.param(
            {"graceful_close_submit_keys": ("",)},
            ("graceful_close_submit_keys", "non-empty strings"),
            id="empty-close-submit-token",
        ),
        pytest.param(
            {"graceful_close_submit_keys": ("SPACE",)},
            ("graceful_close_submit_keys", "unsupported key", "SPACE"),
            id="unknown-close-submit-key",
        ),
    ),
)
def test_interactive_session_support_rejects_malformed_contracts(
    overrides: dict[str, object],
    expected_fragments: tuple[str, ...],
) -> None:
    errors = _provider(_support(**overrides)).validate()

    assert any(
        all(fragment in error for fragment in expected_fragments)
        for error in errors
    ), errors


@pytest.mark.parametrize(
    "forcing_key",
    (
        "ESCAPE",
        "CTRL_C",
        "CTRL_Z",
        "C-c",
        "C-z",
        "SIGINT",
        "SIGTERM",
        "SIGNAL",
        "SUSPEND",
        "CANCEL",
        "RESUME",
        "STEER",
    ),
)
@pytest.mark.parametrize(
    "field_name",
    ("message_submit_keys", "graceful_close_submit_keys"),
)
def test_interactive_session_support_rejects_every_forcing_key_or_action(
    field_name: str,
    forcing_key: str,
) -> None:
    errors = _provider(_support(**{field_name: (forcing_key,)})).validate()

    assert any(
        field_name in error
        and "unsupported key" in error
        and forcing_key in error
        for error in errors
    ), errors


def test_interactive_capability_is_never_inferred_from_adjacent_features() -> None:
    provider = ProviderTemplate(
        name="codex",
        command=["tool", "--tty"],
        input_mode=InputMode.STDIN,
        session_support=ProviderSessionSupport(
            metadata_mode=(
                ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
            ),
            fresh_command=["tool", "--json"],
            resume_command=["tool", "resume", "${SESSION_ID}", "--json"],
            turn_boundary_resume=True,
        ),
    )
    provider.tty_available = True
    provider.observation_support = True

    assert provider.validate() == []
    assert provider.interactive_session_support is None


def test_provider_without_interactive_capability_remains_valid() -> None:
    provider = ProviderTemplate(
        name="ordinary",
        command=["tool", "${PROMPT}"],
        input_mode=InputMode.ARGV,
    )

    assert provider.validate() == []
    assert provider.interactive_session_support is None


def test_builtin_interactive_capability_is_explicit() -> None:
    registry = ProviderRegistry()

    codex = registry.get("codex")
    codex_gpt55 = registry.get("codex_gpt55")
    claude = registry.get("claude")
    gemini = registry.get("gemini")

    assert codex is not None
    assert codex.interactive_session_support is not None
    assert codex.interactive_session_support.schema_version == SCHEMA_VERSION
    assert "${PROMPT}" not in codex.command
    assert "${PROMPT}" in codex.interactive_session_support.command
    assert codex.validate() == []
    assert codex_gpt55 is not None
    assert codex_gpt55.interactive_session_support is None
    assert claude is not None
    assert claude.interactive_session_support is None
    assert gemini is not None
    assert gemini.interactive_session_support is None


def test_workflow_manifest_loads_exact_interactive_capability() -> None:
    registry = ProviderRegistry()

    errors = registry.register_from_workflow(
        {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": _capability_config(),
            }
        }
    )

    assert errors == []
    loaded = registry.get("peer")
    assert loaded is not None
    assert loaded.interactive_session_support == _support()


@pytest.mark.parametrize("missing_field", sorted(CAPABILITY_FIELDS))
def test_workflow_manifest_rejects_missing_interactive_capability_field(
    missing_field: str,
) -> None:
    registry = ProviderRegistry()
    capability = _capability_config()
    del capability[missing_field]

    errors = registry.register_from_workflow(
        {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": capability,
            }
        }
    )

    assert any(
        "interactive_session_support" in error
        and "missing" in error
        and missing_field in error
        for error in errors
    ), errors
    assert registry.get("peer") is None


def test_workflow_manifest_rejects_extra_interactive_capability_field() -> None:
    registry = ProviderRegistry()
    capability = _capability_config(unexpected="value")

    errors = registry.register_from_workflow(
        {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": capability,
            }
        }
    )

    assert any(
        "interactive_session_support" in error
        and "extra" in error
        and "unexpected" in error
        for error in errors
    ), errors
    assert registry.get("peer") is None


def test_workflow_manifest_rejects_non_object_interactive_capability() -> None:
    registry = ProviderRegistry()

    errors = registry.register_from_workflow(
        {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": [],
            }
        }
    )

    assert any(
        "interactive_session_support must be an object" in error
        for error in errors
    ), errors
    assert registry.get("peer") is None


def test_workflow_manifest_rejects_explicit_null_interactive_capability() -> None:
    registry = ProviderRegistry()

    errors = registry.register_from_workflow(
        {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": None,
            }
        }
    )

    assert any(
        "interactive_session_support must be an object" in error
        for error in errors
    ), errors
    assert registry.get("peer") is None


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_type"),
    (
        ("schema_version", 1, "string"),
        ("turn_boundary_messages", 1, "boolean"),
        ("command", ("codex", "${PROMPT}"), "list"),
        ("message_submit_keys", ("ENTER",), "list"),
        ("graceful_close_text", ["/exit"], "string"),
        ("graceful_close_submit_keys", ("ENTER",), "list"),
    ),
)
def test_workflow_manifest_rejects_non_json_capability_field_types(
    field_name: str,
    invalid_value: object,
    expected_type: str,
) -> None:
    registry = ProviderRegistry()

    errors = registry.register_from_workflow(
        {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": _capability_config(
                    **{field_name: invalid_value}
                ),
            }
        }
    )

    assert any(
        field_name in error and expected_type in error
        for error in errors
    ), errors
    assert registry.get("peer") is None


def test_workflow_manifest_absence_does_not_create_capability() -> None:
    registry = ProviderRegistry()

    errors = registry.register_from_workflow(
        {
            "ordinary": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
            }
        }
    )

    assert errors == []
    loaded = registry.get("ordinary")
    assert loaded is not None
    assert loaded.interactive_session_support is None


def _shared_validation_result(
    tmp_path: Path,
    capability: dict[str, object],
) -> WorkflowMappingValidationResult:
    workspace = tmp_path
    mapping = {
        "version": "2.16",
        "name": "interactive-capability-validation",
        "providers": {
            "peer": {
                "command": ["tool", "${PROMPT}"],
                "input_mode": "argv",
                "interactive_session_support": capability,
            }
        },
        "steps": [{"name": "Done", "command": ["echo", "done"]}],
    }
    return validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping=mapping,
            workflow_path=workspace / "interactive-capability.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=workspace,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )


def test_shared_workflow_validation_preserves_valid_capability(
    tmp_path: Path,
) -> None:
    result = _shared_validation_result(tmp_path, _capability_config())

    assert result.errors == ()
    assert result.bundle is not None


def test_shared_workflow_validation_rejects_malformed_capability(
    tmp_path: Path,
) -> None:
    result = _shared_validation_result(
        tmp_path,
        _capability_config(
            schema_version="interactive_terminal_turn_queue.v2"
        ),
    )

    assert result.bundle is None
    assert any(
        "interactive_session_support.schema_version" in error.message
        for error in result.errors
    ), result.errors


class _FakeInteractiveBackend:
    def __init__(self) -> None:
        self.server_started = False
        self.server_live = False
        self.target = "%peer-1"
        self.pane_live = False
        self.pane_status = PaneProcessStatus(
            state="running",
            return_code=None,
        )
        self.pane_status_sequence: list[PaneProcessStatus] = []
        self.started_commands: list[
            tuple[Path, str, tuple[str, ...], Path | None, dict[str, str]]
        ] = []
        self.literal_offers: list[tuple[str, str]] = []
        self.key_offers: list[tuple[str, tuple[str, ...]]] = []
        self.close_pane_calls: list[str] = []
        self.close_server_calls = 0
        self.start_error: InteractiveTerminalError | None = None
        self.start_pane_error: InteractiveTerminalError | None = None
        self.literal_error: InteractiveTerminalError | None = None
        self.key_error: InteractiveTerminalError | None = None
        self.close_pane_error: InteractiveTerminalError | None = None
        self.close_server_error: InteractiveTerminalError | None = None
        self.pane_status_errors: list[
            InteractiveTerminalError | None
        ] = []
        self.server_alive_errors: list[
            InteractiveTerminalError | None
        ] = []

    def start_server(
        self,
        socket_path: Path,
        session_name: str,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, session_name, timeout_sec
        if self.start_error is not None:
            raise self.start_error
        self.server_started = True
        self.server_live = True

    def start_pane(
        self,
        socket_path: Path,
        session_name: str,
        command: Sequence[str],
        *,
        cwd: Path | None,
        env: dict[str, str],
        exit_status_path: Path,
        timeout_sec: float,
    ) -> str:
        del socket_path, exit_status_path, timeout_sec
        if self.start_pane_error is not None:
            raise self.start_pane_error
        self.started_commands.append(
            (Path("opaque"), session_name, tuple(command), cwd, dict(env))
        )
        self.pane_live = True
        return self.target

    def pane_process_status(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> PaneProcessStatus:
        del socket_path, timeout_sec
        if self.pane_status_errors:
            error = self.pane_status_errors.pop(0)
            if error is not None:
                raise error
        if target != self.target or not self.pane_live:
            return PaneProcessStatus(state="missing", return_code=None)
        if self.pane_status_sequence:
            return self.pane_status_sequence.pop(0)
        return self.pane_status

    def server_alive(
        self,
        socket_path: Path,
        session_name: str,
        *,
        timeout_sec: float,
    ) -> bool:
        del socket_path, session_name, timeout_sec
        if self.server_alive_errors:
            error = self.server_alive_errors.pop(0)
            if error is not None:
                raise error
        return self.server_live

    def offer_literal(
        self,
        socket_path: Path,
        target: str,
        literal_text: str,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, timeout_sec
        if self.literal_error is not None:
            raise self.literal_error
        self.literal_offers.append((target, literal_text))

    def offer_keys(
        self,
        socket_path: Path,
        target: str,
        keys: Sequence[str],
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, timeout_sec
        if self.key_error is not None:
            raise self.key_error
        self.key_offers.append((target, tuple(keys)))

    def close_pane(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, timeout_sec
        self.close_pane_calls.append(target)
        if self.close_pane_error is not None:
            raise self.close_pane_error
        self.pane_live = False

    def close_server(
        self,
        socket_path: Path,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, timeout_sec
        self.close_server_calls += 1
        if self.close_server_error is not None:
            raise self.close_server_error
        self.server_live = False


class _ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def monotonic(self) -> float:
        return self.value

    def wait(self, duration: float) -> None:
        self.value += duration


def _interactive_invocation(
    tmp_path: Path,
    *,
    support: InteractiveSessionSupport | None = None,
) -> InteractiveMemberInvocation:
    return InteractiveMemberInvocation(
        invocation_id="invocation-1",
        member_id="reviewer",
        attempt_scope_key="scope-1",
        attempt_ordinal=0,
        resolved_command=("provider-client", "--prompt", "initial"),
        cwd=tmp_path,
        env=MappingProxyType({"EXAMPLE": "1"}),
        support=support or _support(
            message_submit_keys=("ENTER", "TAB"),
        ),
    )


def _interactive_adapter(
    tmp_path: Path,
    backend: _FakeInteractiveBackend,
    clock: _ManualClock | None = None,
) -> InteractiveTerminalTurnQueueAdapter:
    active_clock = clock or _ManualClock()
    return InteractiveTerminalTurnQueueAdapter(
        runtime_root=tmp_path,
        backend=backend,
        monotonic=active_clock.monotonic,
        wait=active_clock.wait,
        poll_interval_sec=0.01,
        operation_timeout_sec=0.5,
    )


def test_interactive_adapter_starts_exact_attempt_bound_handle(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)

    handle = adapter.start(_interactive_invocation(tmp_path))

    assert isinstance(handle, InteractiveMemberHandle)
    assert handle.invocation_id == "invocation-1"
    assert handle.member_id == "reviewer"
    assert handle.attempt_scope_key == "scope-1"
    assert handle.attempt_ordinal == 0
    assert handle.target == backend.target
    assert backend.server_started is True
    [started] = backend.started_commands
    assert started[2] == ("provider-client", "--prompt", "initial")
    assert started[3] == tmp_path
    assert started[4] == {"EXAMPLE": "1"}


def test_interactive_adapter_preserves_literal_multiline_utf8_and_declared_keys(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    message = "first line\nλ second line\n"

    receipt = adapter.offer(handle, message)

    assert isinstance(receipt, OfferReceipt)
    assert receipt.status == "offered"
    assert receipt.byte_count == len(message.encode("utf-8"))
    assert backend.literal_offers == [(backend.target, message)]
    assert backend.key_offers == [(backend.target, ("ENTER", "TAB"))]


def test_interactive_adapter_offers_declared_natural_close_without_forcing(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    receipt = adapter.offer_close(handle)

    assert isinstance(receipt, CloseOfferReceipt)
    assert receipt.status == "close_offered"
    assert backend.literal_offers == [(backend.target, "/exit")]
    assert backend.key_offers == [(backend.target, ("ENTER",))]


def test_interactive_adapter_join_requires_zero_natural_exit_and_full_cleanup(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer_close(handle)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=0,
    )

    proof = adapter.join(handle, deadline=101.0)

    assert isinstance(proof, NaturalShutdownProof)
    assert proof.proof_complete is True
    assert proof.return_code == 0
    assert proof.pane_absent is True
    assert proof.server_absent is True
    assert backend.close_pane_calls == [backend.target]
    assert backend.close_server_calls == 1


def test_tmux_dead_pane_without_recorded_status_remains_unproved() -> None:
    assert interactive_terminal_module._parse_tmux_pane_process_status(
        "1|",
        recorded_exit_status=None,
    ) == PaneProcessStatus(state="exited_pending", return_code=None)


def test_tmux_removed_pane_empty_fields_are_missing() -> None:
    assert interactive_terminal_module._parse_tmux_pane_process_status(
        "|",
        recorded_exit_status=None,
    ) == PaneProcessStatus(state="missing", return_code=None)


def test_tmux_dead_pane_requires_exact_helper_status_for_zero_exit() -> None:
    assert interactive_terminal_module._parse_tmux_pane_process_status(
        "1|",
        recorded_exit_status="0\n",
    ) == PaneProcessStatus(state="exited", return_code=0)


def test_tmux_dead_pane_ignores_unauthoritative_tmux_status() -> None:
    assert interactive_terminal_module._parse_tmux_pane_process_status(
        "1|7",
        recorded_exit_status=None,
    ) == PaneProcessStatus(state="exited_pending", return_code=None)


@pytest.mark.parametrize(
    "recorded_exit_status",
    (
        "",
        "0",
        " 0\n",
        "0 \n",
        "00\n",
        "+0\n",
        "-1\n",
        "256\n",
        "0\n1\n",
        "λ\n",
    ),
)
def test_tmux_dead_pane_rejects_noncanonical_recorded_status(
    recorded_exit_status: str,
) -> None:
    with pytest.raises(InteractiveTerminalError) as exc_info:
        interactive_terminal_module._parse_tmux_pane_process_status(
            "1|",
            recorded_exit_status=recorded_exit_status,
        )

    assert exc_info.value.code == "recorded_exit_status_invalid"


def test_tmux_backend_types_subprocess_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 0.25
        raise subprocess.TimeoutExpired(command, timeout=0.25)

    monkeypatch.setattr(
        interactive_terminal_module.subprocess,
        "run",
        timeout,
    )
    backend = interactive_terminal_module._TmuxInteractiveTerminalBackend()

    with pytest.raises(InteractiveTerminalError) as exc_info:
        backend.server_alive(
            tmp_path / "socket",
            "session",
            timeout_sec=0.25,
        )

    assert exc_info.value.code == "backend_operation_timeout"


def test_interactive_adapter_join_waits_for_recorded_exit_status(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer_close(handle)
    backend.pane_status_sequence = [
        PaneProcessStatus(state="exited_pending", return_code=None),
        PaneProcessStatus(state="exited", return_code=0),
    ]

    proof = adapter.join(handle, deadline=101.0)

    assert proof.proof_complete is True


def test_interactive_adapter_join_is_idempotent_after_natural_shutdown(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer_close(handle)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=0,
    )

    first = adapter.join(handle, deadline=101.0)
    second = adapter.join(handle, deadline=101.0)

    assert second == first
    assert backend.close_pane_calls == [backend.target]
    assert backend.close_server_calls == 1


@pytest.mark.parametrize(
    ("status", "expected_code"),
    (
        (PaneProcessStatus(state="missing", return_code=None), "pane_lost"),
        (PaneProcessStatus(state="exited", return_code=7), "process_failed"),
    ),
)
def test_interactive_adapter_join_rejects_missing_or_failed_process(
    tmp_path: Path,
    status: PaneProcessStatus,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer_close(handle)
    backend.pane_status = status

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.join(handle, deadline=101.0)

    assert exc_info.value.code == expected_code


def test_interactive_adapter_join_times_out_without_screen_authority(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    clock = _ManualClock()
    adapter = _interactive_adapter(tmp_path, backend, clock)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer_close(handle)

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.join(handle, deadline=100.02)

    assert exc_info.value.code == "natural_shutdown_timeout"


@pytest.mark.parametrize(
    ("operation", "backend_error", "expected_code"),
    (
        ("literal", "literal_error", "literal_offer_failed"),
        ("keys", "key_error", "key_offer_failed"),
    ),
)
def test_interactive_adapter_offer_failures_are_typed(
    tmp_path: Path,
    operation: str,
    backend_error: str,
    expected_code: str,
) -> None:
    del operation
    backend = _FakeInteractiveBackend()
    setattr(
        backend,
        backend_error,
        InteractiveTerminalError(expected_code),
    )
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.offer(handle, "message")

    assert exc_info.value.code == expected_code


def test_interactive_adapter_close_failure_is_typed(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.key_error = InteractiveTerminalError("key_offer_failed")
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.offer_close(handle)

    assert exc_info.value.code == "key_offer_failed"


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    (
        ("offer", "offer_timeout"),
        ("offer_close", "close_offer_timeout"),
    ),
)
def test_interactive_adapter_offer_operations_share_one_deadline(
    tmp_path: Path,
    operation: str,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    clock = _ManualClock()
    adapter = _interactive_adapter(tmp_path, backend, clock)
    handle = adapter.start(_interactive_invocation(tmp_path))

    def consume_remaining_budget(
        socket_path: Path,
        target: str,
        literal_text: str,
        *,
        timeout_sec: float,
    ) -> None:
        del socket_path, target, literal_text
        clock.value += timeout_sec

    backend.offer_literal = consume_remaining_budget  # type: ignore[method-assign]

    with pytest.raises(InteractiveTerminalError) as exc_info:
        if operation == "offer":
            adapter.offer(handle, "message")
        else:
            adapter.offer_close(handle)

    assert exc_info.value.code == expected_code
    assert backend.key_offers == []


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    (
        ("offer", "offer_timeout"),
        ("offer_close", "close_offer_timeout"),
    ),
)
def test_interactive_adapter_types_backend_offer_timeouts(
    tmp_path: Path,
    operation: str,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.literal_error = InteractiveTerminalError(
        "backend_operation_timeout"
    )
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    with pytest.raises(InteractiveTerminalError) as exc_info:
        if operation == "offer":
            adapter.offer(handle, "message")
        else:
            adapter.offer_close(handle)

    assert exc_info.value.code == expected_code


@pytest.mark.parametrize(
    ("server_live", "pane_status", "expected_code"),
    (
        (
            False,
            PaneProcessStatus(state="running", return_code=None),
            "server_lost",
        ),
        (
            True,
            PaneProcessStatus(state="missing", return_code=None),
            "pane_lost",
        ),
        (
            True,
            PaneProcessStatus(state="exited", return_code=0),
            "process_not_live",
        ),
    ),
)
def test_interactive_adapter_offer_rejects_lost_process_boundary(
    tmp_path: Path,
    server_live: bool,
    pane_status: PaneProcessStatus,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    backend.server_live = server_live
    backend.pane_status = pane_status

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.offer(handle, "message")

    assert exc_info.value.code == expected_code
    assert backend.literal_offers == []


def test_interactive_adapter_start_failure_closes_private_server(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.start_pane_error = InteractiveTerminalError(
        "pane_start_failed"
    )
    adapter = _interactive_adapter(tmp_path, backend)

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.start(_interactive_invocation(tmp_path))

    assert exc_info.value.code == "pane_start_failed"
    assert backend.close_server_calls == 1
    assert backend.server_live is False


def test_interactive_adapter_rejects_foreign_and_stale_handles(
    tmp_path: Path,
) -> None:
    first_backend = _FakeInteractiveBackend()
    second_backend = _FakeInteractiveBackend()
    first = _interactive_adapter(tmp_path / "first", first_backend)
    second = _interactive_adapter(tmp_path / "second", second_backend)
    handle = first.start(_interactive_invocation(tmp_path / "first"))

    with pytest.raises(InteractiveTerminalError) as foreign:
        second.offer(handle, "message")
    assert foreign.value.code == "foreign_handle"

    proof = first.abort(handle, deadline=101.0)
    assert isinstance(proof, FailedCleanupProof)
    with pytest.raises(InteractiveTerminalError) as stale:
        first.offer(handle, "later")
    assert stale.value.code == "handle_terminal"


def test_interactive_adapter_abort_is_cleanup_only_and_reports_failure(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    proof = adapter.abort(handle, deadline=101.0)

    assert isinstance(proof, FailedCleanupProof)
    assert proof.disposition == "failed_cleanup"
    assert proof.cleanup_complete is True
    assert proof.pane_absent is True
    assert proof.server_absent is True
    assert not isinstance(proof, NaturalShutdownProof)


def test_interactive_adapter_abort_surfaces_incomplete_cleanup(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.close_server_error = InteractiveTerminalError(
        "server_teardown_failed"
    )
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    proof = adapter.abort(handle, deadline=101.0)

    assert proof.cleanup_complete is False
    assert proof.server_absent is False
    assert proof.error_code == "server_teardown_failed"


@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    (
        ("final_pane_probe", "pane_probe_failed"),
        ("final_server_probe", "server_probe_failed"),
    ),
)
def test_interactive_adapter_abort_returns_proof_when_final_probe_fails(
    tmp_path: Path,
    boundary: str,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    if boundary == "final_pane_probe":
        backend.pane_status_errors = [
            None,
            InteractiveTerminalError(expected_code),
        ]
    else:
        backend.server_alive_errors = [
            None,
            InteractiveTerminalError(expected_code),
        ]

    proof = adapter.abort(handle, deadline=101.0)

    assert proof.cleanup_complete is False
    assert proof.error_code == expected_code
    if boundary == "final_pane_probe":
        assert proof.pane_absent is False
        assert proof.server_absent is True
    else:
        assert proof.pane_absent is True
        assert proof.server_absent is False


@pytest.mark.parametrize(
    ("boundary", "expected_code"),
    (
        ("initial_pane_probe", "pane_probe_failed"),
        ("initial_server_probe", "server_probe_failed"),
    ),
)
def test_interactive_adapter_abort_attempts_teardown_after_initial_probe_failure(
    tmp_path: Path,
    boundary: str,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    if boundary == "initial_pane_probe":
        backend.pane_status_errors = [
            InteractiveTerminalError(expected_code),
        ]
    else:
        backend.server_alive_errors = [
            InteractiveTerminalError(expected_code),
        ]

    proof = adapter.abort(handle, deadline=101.0)

    assert proof.cleanup_complete is False
    assert proof.error_code == expected_code
    assert proof.pane_absent is True
    assert proof.server_absent is True
    assert backend.close_pane_calls == [backend.target]
    assert backend.close_server_calls == 1


def test_interactive_adapter_abort_at_expired_deadline_is_total(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))

    proof = adapter.abort(handle, deadline=100.0)

    assert proof.cleanup_complete is False
    assert proof.pane_absent is False
    assert proof.server_absent is False
    assert proof.error_code == "cleanup_timeout"
    assert backend.close_pane_calls == []
    assert backend.close_server_calls == 0
    assert adapter.abort(handle, deadline=101.0) == proof


def test_interactive_adapter_abort_after_failed_join_remains_cleanup_only(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer_close(handle)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=7,
    )
    with pytest.raises(InteractiveTerminalError):
        adapter.join(handle, deadline=101.0)

    proof = adapter.abort(handle, deadline=101.0)

    assert proof.disposition == "failed_cleanup"
    assert proof.cleanup_complete is True
    assert not isinstance(proof, NaturalShutdownProof)


def test_interactive_adapter_never_uses_v1_control_or_observation_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("interactive adapter crossed into a v1 forcing surface")

    monkeypatch.setattr(
        "orchestrator.providers.control.ProviderExecutionControl.request_cancel",
        forbidden,
    )
    monkeypatch.setattr(
        "orchestrator.providers.control.ProviderExecutionControl.cancel_and_reap",
        forbidden,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.provider_supervision.bindings."
        "WorkflowProviderSupervisionBindings.prepare_resume_invocation",
        forbidden,
    )
    monkeypatch.setattr(
        "orchestrator.providers.executor.ProviderExecutor.prepare_invocation",
        forbidden,
    )
    monkeypatch.setattr(
        "orchestrator.providers.observation.ProviderObservationManager.open_observation",
        forbidden,
    )
    monkeypatch.setattr(
        "orchestrator.workflow.provider_supervision.directive."
        "ProviderSteeringDirective.from_dict",
        forbidden,
    )
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = adapter.start(_interactive_invocation(tmp_path))
    adapter.offer(handle, "queued")
    adapter.offer_close(handle)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=0,
    )

    proof = adapter.join(handle, deadline=101.0)

    assert proof.proof_complete is True
