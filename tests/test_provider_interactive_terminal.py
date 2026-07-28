"""Structural provider capability tests for interactive terminal sessions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import MappingProxyType
from typing import Callable, Sequence

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
    NoBackendAllocationProof,
    OfferReceipt,
    PaneProcessStatus,
)
from orchestrator.providers.executor import ProviderExecutor


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


def test_provider_executor_prepares_exact_interactive_member_invocation(
    tmp_path: Path,
) -> None:
    registry = ProviderRegistry()
    registry.register(
        ProviderTemplate(
            name="peer-provider",
            command=["ordinary", "${PROMPT}"],
            defaults={"model": "peer-model"},
            input_mode=InputMode.ARGV,
            interactive_session_support=InteractiveSessionSupport(
                schema_version=SCHEMA_VERSION,
                turn_boundary_messages=True,
                command=(
                    "interactive",
                    "--model",
                    "${model}",
                    "${PROMPT}",
                ),
                message_submit_keys=("ENTER",),
                graceful_close_text="/exit",
                graceful_close_submit_keys=("ENTER",),
            ),
        )
    )
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_interactive_invocation(
        provider_name="peer-provider",
        params={},
        context={},
        prompt_content="literal prompt\nsecond line",
        invocation_id="invocation-1",
        member_id="reviewer",
        attempt_scope_key="sha256:" + "a" * 64,
        attempt_ordinal=3,
        cwd=tmp_path,
        env={"ORCHESTRATOR_ACTIVE_PEER_BINDING": "opaque"},
        provider_call_policy={
            "delivery": "phased",
            "materialization_attempts": 2,
        },
    )

    assert error is None
    assert invocation is not None
    assert invocation.resolved_command == (
        "interactive",
        "--model",
        "peer-model",
        "literal prompt\nsecond line",
    )
    assert invocation.pre_prompt_command == (
        "interactive",
        "--model",
        "peer-model",
        "${PROMPT}",
    )
    assert invocation.invocation_id == "invocation-1"
    assert invocation.member_id == "reviewer"
    assert invocation.attempt_scope_key == "sha256:" + "a" * 64
    assert invocation.attempt_ordinal == 3
    assert invocation.cwd == tmp_path
    assert invocation.env["ORCHESTRATOR_ACTIVE_PEER_BINDING"] == "opaque"
    assert invocation.support.schema_version == SCHEMA_VERSION


def test_builtin_codex_prepares_policy_resolved_pre_prompt_command(
    tmp_path: Path,
) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())

    invocation, error = executor.prepare_interactive_invocation(
        provider_name="codex",
        params={},
        context={},
        prompt_content="task turn",
        invocation_id="invocation-built-in",
        member_id="reviewer",
        attempt_scope_key="sha256:" + "b" * 64,
        attempt_ordinal=1,
        cwd=tmp_path,
        provider_call_policy={
            "model": "policy-model",
            "effort": "medium",
            "delivery": "phased",
            "materialization_attempts": 2,
        },
    )

    assert error is None
    assert invocation is not None
    assert invocation.pre_prompt_command[:5] == (
        "codex",
        "--model",
        "policy-model",
        "--config",
        "reasoning_effort=medium",
    )
    assert invocation.pre_prompt_command[-1:] == (
        "${PROMPT}",
    )
    assert invocation.resolved_command[:5] == (
        "codex",
        "--model",
        "policy-model",
        "--config",
        "reasoning_effort=medium",
    )
    assert invocation.resolved_command[-1:] == (
        "task turn",
    )
    assert all(
        "delivery" not in token and "materialization" not in token
        for token in invocation.pre_prompt_command
    )


def test_provider_executor_preserves_placeholder_syntax_inside_literal_prompt(
    tmp_path: Path,
) -> None:
    registry = ProviderRegistry()
    registry.register(_provider(_support()))
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_interactive_invocation(
        provider_name="peer-provider",
        params={},
        context={},
        prompt_content="Explain literal ${name} syntax.",
        invocation_id="invocation-1",
        member_id="reviewer",
        attempt_scope_key="sha256:" + "c" * 64,
        attempt_ordinal=1,
        cwd=tmp_path,
    )

    assert error is None
    assert invocation is not None
    assert invocation.resolved_command == (
        "codex",
        "Explain literal ${name} syntax.",
    )


def test_interactive_invocation_rejects_placeholder_outside_prompt_token(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="resolved_command must not contain placeholders",
    ):
        InteractiveMemberInvocation(
            invocation_id="invocation-1",
            member_id="reviewer",
            attempt_scope_key="sha256:" + "d" * 64,
            attempt_ordinal=1,
            resolved_command=(
                "codex",
                "literal ${name}",
                "${unresolved}",
            ),
            cwd=tmp_path,
            env=MappingProxyType({"LITERAL": "${context.value}"}),
            support=_support(),
        )


def test_provider_executor_revalidates_interactive_capability_before_launch(
    tmp_path: Path,
) -> None:
    registry = ProviderRegistry()
    provider = _provider(_support())
    registry.register(provider)
    provider.interactive_session_support = _support(
        schema_version="interactive_terminal_turn_queue.v2"
    )
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_interactive_invocation(
        provider_name="peer-provider",
        params={},
        context={},
        prompt_content="prompt",
        invocation_id="invocation-1",
        member_id="writer",
        attempt_scope_key="sha256:" + "b" * 64,
        attempt_ordinal=1,
        cwd=tmp_path,
    )

    assert invocation is None
    assert error is not None
    assert error["type"] == "interactive_session_capability_invalid"


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
    assert codex.interactive_session_support.graceful_close_submit_keys == (
        "ENTER",
        "TAB",
    )
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
        self.server_envs: list[dict[str, str]] = []
        self.started_commands: list[
            tuple[Path, str, tuple[str, ...], Path | None]
        ] = []
        self.literal_offers: list[tuple[str, str]] = []
        self.key_offers: list[tuple[str, tuple[str, ...]]] = []
        self.close_pane_calls: list[str] = []
        self.close_server_calls = 0
        self.actions: list[tuple[str, float]] = []
        self.after_action: dict[str, Callable[[], None]] = {}
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
        env: dict[str, str],
        timeout_sec: float,
    ) -> None:
        del socket_path, session_name
        self.actions.append(("start_server", timeout_sec))
        callback = self.after_action.get("start_server")
        if callback is not None:
            callback()
        if self.start_error is not None:
            raise self.start_error
        self.server_started = True
        self.server_live = True
        self.server_envs.append(dict(env))

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
        del socket_path, exit_status_path
        self.actions.append(("start_pane", timeout_sec))
        callback = self.after_action.get("start_pane")
        if callback is not None:
            callback()
        if self.start_pane_error is not None:
            raise self.start_pane_error
        self.started_commands.append(
            (Path("opaque"), session_name, tuple(command), cwd)
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
        del socket_path
        self.actions.append(("pane_process_status", timeout_sec))
        callback = self.after_action.get("pane_process_status")
        if callback is not None:
            callback()
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
        del socket_path, session_name
        self.actions.append(("server_alive", timeout_sec))
        callback = self.after_action.get("server_alive")
        if callback is not None:
            callback()
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
        del socket_path
        self.actions.append(("offer_literal", timeout_sec))
        callback = self.after_action.get("offer_literal")
        if callback is not None:
            callback()
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
        del socket_path
        self.actions.append(("offer_keys", timeout_sec))
        callback = self.after_action.get("offer_keys")
        if callback is not None:
            callback()
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
        del socket_path
        self.actions.append(("close_pane", timeout_sec))
        callback = self.after_action.get("close_pane")
        if callback is not None:
            callback()
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
        del socket_path
        self.actions.append(("close_server", timeout_sec))
        callback = self.after_action.get("close_server")
        if callback is not None:
            callback()
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
        socket_root=Path(tempfile.gettempdir()),
        backend=backend,
        monotonic=active_clock.monotonic,
        wait=active_clock.wait,
        poll_interval_sec=0.01,
        operation_timeout_sec=0.5,
    )


def _p1_type(name: str) -> type[object]:
    value = getattr(interactive_terminal_module, name, None)
    assert isinstance(value, type), f"{name} must be implemented"
    return value


def _started_handle(
    adapter: InteractiveTerminalTurnQueueAdapter,
    invocation: InteractiveMemberInvocation,
    *,
    deadline: float,
) -> InteractiveMemberHandle:
    outcome = adapter.start(invocation, deadline=deadline)
    start_outcome_type = _p1_type("InteractiveTerminalStartOutcome")
    assert type(outcome) is start_outcome_type
    assert outcome.status == "started"
    assert isinstance(outcome.handle, InteractiveMemberHandle)
    return outcome.handle


def test_interactive_adapter_start_outcome_is_closed_and_immutable(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)

    outcome = adapter.start(
        _interactive_invocation(tmp_path),
        deadline=100.25,
    )

    start_outcome_type = _p1_type("InteractiveTerminalStartOutcome")
    assert type(outcome) is start_outcome_type
    assert outcome.status == "started"
    assert isinstance(outcome.handle, InteractiveMemberHandle)
    assert outcome.to_dict() == {
        "status": "started",
        "handle": outcome.handle,
    }
    with pytest.raises(FrozenInstanceError):
        outcome.status = "failed"


def test_interactive_adapter_issues_pristine_no_allocation_proof_once(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)

    proof = adapter.prove_no_backend_allocation()

    assert proof == NoBackendAllocationProof(
        disposition="no_backend_allocation",
        backend_resource_allocated=False,
        proof_complete=True,
    )
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=100.25,
    )
    assert handle is not None
    with pytest.raises(InteractiveTerminalError, match="handle_terminal"):
        adapter.prove_no_backend_allocation()


@pytest.mark.parametrize(
    "status",
    (
        PaneProcessStatus(state="running", return_code=None),
        PaneProcessStatus(state="exited_pending", return_code=None),
        PaneProcessStatus(state="exited", return_code=0),
        PaneProcessStatus(state="exited", return_code=7),
    ),
)
def test_interactive_adapter_process_probe_is_non_destructive(
    tmp_path: Path,
    status: PaneProcessStatus,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=100.25,
    )
    backend.pane_status = status

    assert adapter.probe_process_status(
        handle,
        deadline=100.25,
    ) == status
    assert adapter.probe_process_status(
        handle,
        deadline=100.25,
    ) == status


def test_interactive_adapter_start_outcome_before_deadline_proves_no_allocation(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)

    outcome = adapter.start(
        _interactive_invocation(tmp_path),
        deadline=100.0,
    )

    no_allocation_type = _p1_type("NoBackendAllocationProof")
    assert outcome.to_dict() == {
        "status": "failed",
        "error_code": "start_timeout",
        "backend_allocation": "none",
        "cleanup_status": "not_required",
        "provider_zero_survivor_proven": True,
        "proof": no_allocation_type(
            disposition="no_backend_allocation",
            backend_resource_allocated=False,
            proof_complete=True,
        ),
    }
    assert backend.actions == []


def test_interactive_adapter_start_outcome_complete_cleanup_is_handle_free(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.start_pane_error = InteractiveTerminalError("pane_start_failed")
    adapter = _interactive_adapter(tmp_path, backend)

    outcome = adapter.start(
        _interactive_invocation(tmp_path),
        deadline=100.5,
    )

    cleanup_type = _p1_type("PhasedFailedCleanupEvidence")
    assert outcome.status == "failed"
    assert outcome.error_code == "pane_start_failed"
    assert outcome.backend_allocation == "possible_or_allocated"
    assert outcome.cleanup_status == "completed"
    assert outcome.provider_zero_survivor_proven is True
    assert type(outcome.proof) is cleanup_type
    assert outcome.proof == cleanup_type(
        disposition="failed_cleanup",
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )
    assert "handle" not in outcome.to_dict()
    assert not isinstance(outcome.proof, FailedCleanupProof)


def test_interactive_adapter_start_outcome_incomplete_cleanup_maps_production_token(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.start_pane_error = InteractiveTerminalError("pane_start_failed")
    backend.close_server_error = InteractiveTerminalError(
        "server_teardown_failed"
    )
    adapter = _interactive_adapter(tmp_path, backend)

    outcome = adapter.start(
        _interactive_invocation(tmp_path),
        deadline=100.5,
    )

    cleanup_type = _p1_type("PhasedFailedCleanupEvidence")
    assert outcome.error_code == (
        "interactive_terminal_start_cleanup_incomplete"
    )
    assert outcome.backend_allocation == "possible_or_allocated"
    assert outcome.cleanup_status == "incomplete"
    assert outcome.provider_zero_survivor_proven is False
    assert outcome.proof == cleanup_type(
        disposition="failed_cleanup",
        pane_absent=False,
        server_absent=False,
        cleanup_complete=False,
        error_code="interactive_terminal_start_cleanup_incomplete",
    )
    assert "handle" not in outcome.to_dict()
    assert not isinstance(outcome.proof, FailedCleanupProof)


def test_interactive_adapter_start_outcome_rejects_missing_handle_inference() -> None:
    start_outcome_type = _p1_type("InteractiveTerminalStartOutcome")
    no_allocation_type = _p1_type("NoBackendAllocationProof")

    with pytest.raises(ValueError):
        start_outcome_type(
            status="failed",
            error_code="pane_start_failed",
            backend_allocation="possible_or_allocated",
            cleanup_status="not_required",
            provider_zero_survivor_proven=True,
            proof=no_allocation_type(
                disposition="no_backend_allocation",
                backend_resource_allocated=False,
                proof_complete=True,
            ),
        )


@pytest.mark.parametrize(
    "deadline",
    (True, float("nan"), float("inf"), float("-inf")),
)
@pytest.mark.parametrize(
    "operation",
    ("start", "offer", "close", "join", "abort"),
)
def test_interactive_adapter_deadline_requires_finite_absolute_timestamp(
    tmp_path: Path,
    operation: str,
    deadline: float,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    if operation == "start":
        with pytest.raises(ValueError, match="monotonic timestamp"):
            adapter.start(
                _interactive_invocation(tmp_path),
                deadline=deadline,
            )
        assert backend.actions == []
        return

    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    backend.actions.clear()
    with pytest.raises(ValueError, match="monotonic timestamp"):
        if operation == "offer":
            adapter.offer(handle, "message", deadline=deadline)
        elif operation == "close":
            adapter.offer_close(handle, deadline=deadline)
        elif operation == "join":
            adapter.join(handle, deadline=deadline)
        else:
            adapter.abort(handle, deadline=deadline)
    assert backend.actions == []


def test_project_phased_failed_cleanup_proof_requires_exact_active_handle() -> None:
    cleanup_type = _p1_type("PhasedFailedCleanupEvidence")
    project = getattr(
        interactive_terminal_module,
        "project_phased_failed_cleanup_evidence",
        None,
    )
    assert callable(project)
    proof = FailedCleanupProof(
        disposition="failed_cleanup",
        handle_id="active-handle",
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )

    assert project(
        proof,
        active_handle_id="active-handle",
    ) == cleanup_type(
        disposition="failed_cleanup",
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )


@pytest.mark.parametrize(
    "proof,active_handle_id",
    (
        (
            {
                "disposition": "failed_cleanup",
                "handle_id": "active-handle",
                "pane_absent": True,
                "server_absent": True,
                "cleanup_complete": True,
                "error_code": None,
            },
            "active-handle",
        ),
        (
            {
                "disposition": "failed_cleanup",
                "handle_id": "active-handle",
                "pane_absent": True,
                "server_absent": True,
                "cleanup_complete": True,
                "error_code": None,
                "extra": True,
            },
            "active-handle",
        ),
        (
            FailedCleanupProof(
                disposition="failed_cleanup",
                handle_id="active-handle",
                pane_absent=1,
                server_absent=True,
                cleanup_complete=True,
                error_code=None,
            ),
            "active-handle",
        ),
        (
            FailedCleanupProof(
                disposition="failed_cleanup",
                handle_id="active-handle",
                pane_absent=False,
                server_absent=False,
                cleanup_complete=False,
                error_code="unknown_cleanup_token",
            ),
            "active-handle",
        ),
        (
            FailedCleanupProof(
                disposition="failed_cleanup",
                handle_id="other-handle",
                pane_absent=True,
                server_absent=True,
                cleanup_complete=True,
                error_code=None,
            ),
            "active-handle",
        ),
    ),
)
def test_project_phased_failed_cleanup_proof_fails_closed(
    proof: object,
    active_handle_id: str,
) -> None:
    project = getattr(
        interactive_terminal_module,
        "project_phased_failed_cleanup_evidence",
        None,
    )
    assert callable(project)

    assert project(proof, active_handle_id=active_handle_id) is None


@pytest.mark.parametrize(
    ("operation", "expected_code"),
    (
        ("offer", "offer_timeout"),
        ("close", "close_offer_timeout"),
    ),
)
def test_interactive_adapter_offer_deadline_expiry_starts_zero_backend_actions(
    tmp_path: Path,
    operation: str,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=100.5,
    )
    backend.actions.clear()

    with pytest.raises(InteractiveTerminalError) as exc_info:
        if operation == "offer":
            adapter.offer(handle, "message", deadline=100.0)
        else:
            adapter.offer_close(handle, deadline=100.0)

    assert exc_info.value.code == expected_code
    assert backend.actions == []


@pytest.mark.parametrize("operation", ("start", "offer", "close"))
def test_interactive_adapter_deadline_limits_every_selected_backend_action(
    tmp_path: Path,
    operation: str,
) -> None:
    backend = _FakeInteractiveBackend()
    clock = _ManualClock()
    adapter = _interactive_adapter(tmp_path, backend, clock)
    if operation == "start":
        outcome = adapter.start(
            _interactive_invocation(tmp_path),
            deadline=100.125,
        )
        assert outcome.status == "started"
    else:
        handle = _started_handle(
            adapter,
            _interactive_invocation(tmp_path),
            deadline=100.5,
        )
        backend.actions.clear()
        if operation == "offer":
            adapter.offer(handle, "message", deadline=100.125)
        else:
            adapter.offer_close(handle, deadline=100.125)

    assert backend.actions
    assert all(0.0 < timeout <= 0.125 for _, timeout in backend.actions)


@pytest.mark.parametrize(
    ("operation", "expiring_action", "expected_code"),
    (
        ("start", "start_server", "interactive_terminal_start_cleanup_incomplete"),
        ("offer", "server_alive", "offer_timeout"),
        ("close", "server_alive", "close_offer_timeout"),
    ),
)
def test_interactive_adapter_during_operation_deadline_starts_no_later_action(
    tmp_path: Path,
    operation: str,
    expiring_action: str,
    expected_code: str,
) -> None:
    backend = _FakeInteractiveBackend()
    clock = _ManualClock()
    adapter = _interactive_adapter(tmp_path, backend, clock)
    if operation != "start":
        handle = _started_handle(
            adapter,
            _interactive_invocation(tmp_path),
            deadline=100.5,
        )
        backend.actions.clear()
    backend.after_action[expiring_action] = lambda: setattr(
        clock,
        "value",
        100.125,
    )

    if operation == "start":
        outcome = adapter.start(
            _interactive_invocation(tmp_path),
            deadline=100.125,
        )
        assert outcome.status == "failed"
        assert outcome.error_code == expected_code
    else:
        with pytest.raises(InteractiveTerminalError) as exc_info:
            if operation == "offer":
                adapter.offer(handle, "message", deadline=100.125)
            else:
                adapter.offer_close(handle, deadline=100.125)
        assert exc_info.value.code == expected_code

    action_names = [name for name, _ in backend.actions]
    assert action_names == [expiring_action]


def test_interactive_adapter_separates_short_socket_from_runtime_artifacts(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / ("runtime-" + ("r" * 100))
    with tempfile.TemporaryDirectory(
        prefix="orc-peer-sockets-",
        dir="/tmp",
    ) as socket_root_text:
        socket_root = Path(socket_root_text)
        adapters = tuple(
            InteractiveTerminalTurnQueueAdapter(
                runtime_root=runtime_root,
                socket_root=socket_root,
                backend=_FakeInteractiveBackend(),
            )
            for _ in range(2)
        )
        handles = tuple(
            _started_handle(
                adapter,
                _interactive_invocation(tmp_path),
                deadline=time.monotonic() + 5.0,
            )
            for adapter in adapters
        )

        assert all(
            handle.socket_path.parent == socket_root
            and handle.socket_path.name.startswith("orc-peer-")
            and handle.socket_path.name.endswith(".sock")
            and len(os.fsencode(handle.socket_path)) <= 103
            for handle in handles
        )
        assert handles[0].socket_path != handles[1].socket_path
        assert len(
            os.fsencode(runtime_root / handles[0].socket_path.name)
        ) > 103
        assert all(
            adapter._exit_status_path.is_relative_to(runtime_root)
            for adapter in adapters
        )


def test_interactive_adapter_rejects_long_socket_path_before_backend_start(
    tmp_path: Path,
) -> None:
    socket_root = tmp_path / ("socket-" + ("s" * 120))
    socket_root.mkdir()
    runtime_root = tmp_path / "runtime-artifacts"
    backend = _FakeInteractiveBackend()

    with pytest.raises(InteractiveTerminalError) as exc_info:
        InteractiveTerminalTurnQueueAdapter(
            runtime_root=runtime_root,
            socket_root=socket_root,
            backend=backend,
        )

    assert exc_info.value.code == (
        "interactive_terminal_socket_path_unavailable"
    )
    assert backend.server_started is False
    assert not runtime_root.exists()


def test_interactive_adapter_starts_exact_attempt_bound_handle(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)

    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

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
    assert backend.server_envs == [{"EXAMPLE": "1"}]


def test_interactive_adapter_preserves_literal_multiline_utf8_and_declared_keys(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    message = "first line\nλ second line\n"

    receipt = adapter.offer(handle, message, deadline=101.0)

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

    receipt = adapter.offer_close(handle, deadline=101.0)

    assert isinstance(receipt, CloseOfferReceipt)
    assert receipt.status == "close_offered"
    assert backend.literal_offers == [(backend.target, "/exit")]
    assert backend.key_offers == [(backend.target, ("ENTER",))]


def test_interactive_adapter_join_requires_zero_natural_exit_and_full_cleanup(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer_close(handle, deadline=101.0)
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


def test_interactive_adapter_natural_join_removes_owned_socket_after_absence(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    handle.socket_path.touch()
    adapter.offer_close(handle, deadline=101.0)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=0,
    )

    proof = adapter.join(handle, deadline=101.0)

    assert proof.server_absent is True
    assert backend.server_live is False
    assert not handle.socket_path.exists()


def test_interactive_adapter_natural_join_types_socket_unlink_failure(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    handle.socket_path.mkdir()
    adapter.offer_close(handle, deadline=101.0)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=0,
    )

    try:
        with pytest.raises(InteractiveTerminalError) as exc_info:
            adapter.join(handle, deadline=101.0)
        assert exc_info.value.code == (
            "interactive_terminal_socket_cleanup_failed"
        )
        assert backend.server_live is False
        assert handle.socket_path.is_dir()
    finally:
        handle.socket_path.rmdir()


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


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is unavailable")
def test_tmux_backend_inherits_exact_composed_environment_from_private_server(
) -> None:
    environment = os.environ.copy()
    environment["ORC_TEST_SEMICOLON"] = "history -a;_fasd_prompt_func;"
    environment["ORC_TEST_NEWLINE"] = "first\nsecond"

    with tempfile.TemporaryDirectory(prefix="orc-peer-env-") as root_text:
        root = Path(root_text)
        socket_path = root / "tmux.sock"
        status_path = root / "provider.exit-status"
        observed_path = root / "observed.json"
        release_path = root / "release"
        multiline_argument = "first; 'quoted' value\nsecond line"
        backend = (
            interactive_terminal_module._TmuxInteractiveTerminalBackend()
        )
        target: str | None = None
        backend.start_server(
            socket_path,
            "peer-env",
            env=environment,
            timeout_sec=5.0,
        )
        try:
            script = "\n".join(
                (
                    "import json, os, sys, time",
                    "from pathlib import Path",
                    f"observed = Path({str(observed_path)!r})",
                    f"release = Path({str(release_path)!r})",
                    "observed.write_text(json.dumps({",
                    "    'semicolon': os.environ['ORC_TEST_SEMICOLON'],",
                    "    'newline': os.environ['ORC_TEST_NEWLINE'],",
                    "    'argument': sys.argv[1],",
                    "}), encoding='utf-8')",
                    "deadline = time.monotonic() + 5.0",
                    (
                        "while not release.exists() "
                        "and time.monotonic() < deadline:"
                    ),
                    "    time.sleep(0.01)",
                    "raise SystemExit(0 if release.exists() else 3)",
                )
            )
            target = backend.start_pane(
                socket_path,
                "peer-env",
                (sys.executable, "-c", script, multiline_argument),
                cwd=root,
                exit_status_path=status_path,
                timeout_sec=5.0,
            )
            deadline = time.monotonic() + 2.0
            while not observed_path.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert json.loads(observed_path.read_text(encoding="utf-8")) == {
                "semicolon": "history -a;_fasd_prompt_func;",
                "newline": "first\nsecond",
                "argument": multiline_argument,
            }
            release_path.write_text("release\n", encoding="ascii")
            deadline = time.monotonic() + 2.0
            status = backend.pane_process_status(
                socket_path,
                target,
                timeout_sec=1.0,
            )
            while (
                status.state != "exited"
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
                status = backend.pane_process_status(
                    socket_path,
                    target,
                    timeout_sec=1.0,
                )
            assert status == PaneProcessStatus(
                state="exited",
                return_code=0,
            )
            assert status_path.read_text(encoding="ascii") == "0\n"
        finally:
            if target is not None:
                backend.close_pane(
                    socket_path,
                    target,
                    timeout_sec=5.0,
                )
            backend.close_server(socket_path, timeout_sec=5.0)


def test_interactive_adapter_join_waits_for_recorded_exit_status(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer_close(handle, deadline=101.0)
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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer_close(handle, deadline=101.0)
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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer_close(handle, deadline=101.0)
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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer_close(handle, deadline=101.0)

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.offer(handle, "message", deadline=101.0)

    assert exc_info.value.code == expected_code


def test_interactive_adapter_close_failure_is_typed(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.key_error = InteractiveTerminalError("key_offer_failed")
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.offer_close(handle, deadline=101.0)

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

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
            adapter.offer(handle, "message", deadline=100.5)
        else:
            adapter.offer_close(handle, deadline=100.5)

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

    with pytest.raises(InteractiveTerminalError) as exc_info:
        if operation == "offer":
            adapter.offer(handle, "message", deadline=101.0)
        else:
            adapter.offer_close(handle, deadline=101.0)

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    backend.server_live = server_live
    backend.pane_status = pane_status

    with pytest.raises(InteractiveTerminalError) as exc_info:
        adapter.offer(handle, "message", deadline=101.0)

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
    adapter._socket_path.touch()

    outcome = adapter.start(
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

    assert outcome.status == "failed"
    assert outcome.error_code == "pane_start_failed"
    assert outcome.cleanup_status == "completed"
    assert backend.close_server_calls == 1
    assert backend.server_live is False
    assert not adapter._socket_path.exists()


@pytest.mark.parametrize(
    "start_error",
    (
        InteractiveTerminalError("pane_start_failed"),
        OSError("pane start failed"),
    ),
)
def test_interactive_adapter_start_failure_requires_complete_socket_cleanup(
    tmp_path: Path,
    start_error: Exception,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.start_pane_error = start_error  # type: ignore[assignment]
    adapter = _interactive_adapter(tmp_path, backend)
    adapter._socket_path.mkdir()

    try:
        outcome = adapter.start(
            _interactive_invocation(tmp_path),
            deadline=101.0,
        )
        assert outcome.status == "failed"
        assert outcome.error_code == (
            "interactive_terminal_start_cleanup_incomplete"
        )
        assert outcome.cleanup_status == "incomplete"
        assert backend.server_live is False
        assert adapter._socket_path.is_dir()
        assert adapter._natural_proof is None
        assert adapter._cleanup_proof is None
        assert adapter._state == "failed"
    finally:
        adapter._socket_path.rmdir()


def test_interactive_adapter_rejects_foreign_and_stale_handles(
    tmp_path: Path,
) -> None:
    first_backend = _FakeInteractiveBackend()
    second_backend = _FakeInteractiveBackend()
    first = _interactive_adapter(tmp_path / "first", first_backend)
    second = _interactive_adapter(tmp_path / "second", second_backend)
    handle = _started_handle(
        first,
        _interactive_invocation(tmp_path / "first"),
        deadline=101.0,
    )

    with pytest.raises(InteractiveTerminalError) as foreign:
        second.offer(handle, "message", deadline=101.0)
    assert foreign.value.code == "foreign_handle"

    proof = first.abort(handle, deadline=101.0)
    assert isinstance(proof, FailedCleanupProof)
    with pytest.raises(InteractiveTerminalError) as stale:
        first.offer(handle, "later", deadline=101.0)
    assert stale.value.code == "handle_terminal"


def test_interactive_adapter_abort_is_cleanup_only_and_reports_failure(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    handle.socket_path.touch()

    proof = adapter.abort(handle, deadline=101.0)

    assert isinstance(proof, FailedCleanupProof)
    assert proof.disposition == "failed_cleanup"
    assert proof.cleanup_complete is True
    assert proof.pane_absent is True
    assert proof.server_absent is True
    assert not handle.socket_path.exists()
    assert not isinstance(proof, NaturalShutdownProof)


def test_interactive_adapter_abort_reports_owned_socket_unlink_failure(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    handle.socket_path.mkdir()

    try:
        proof = adapter.abort(handle, deadline=101.0)
        assert proof.server_absent is True
        assert proof.cleanup_complete is False
        assert proof.error_code == (
            "interactive_terminal_socket_cleanup_failed"
        )
        assert handle.socket_path.is_dir()
    finally:
        handle.socket_path.rmdir()


def test_interactive_adapter_abort_surfaces_incomplete_cleanup(
    tmp_path: Path,
) -> None:
    backend = _FakeInteractiveBackend()
    backend.close_server_error = InteractiveTerminalError(
        "server_teardown_failed"
    )
    adapter = _interactive_adapter(tmp_path, backend)
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )

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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer_close(handle, deadline=101.0)
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
    handle = _started_handle(
        adapter,
        _interactive_invocation(tmp_path),
        deadline=101.0,
    )
    adapter.offer(handle, "queued", deadline=101.0)
    adapter.offer_close(handle, deadline=101.0)
    backend.pane_status = PaneProcessStatus(
        state="exited",
        return_code=0,
    )

    proof = adapter.join(handle, deadline=101.0)

    assert proof.proof_complete is True
