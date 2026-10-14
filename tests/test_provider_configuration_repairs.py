from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.providers import (
    ProviderExecutor,
    ProviderParams,
    ProviderRegistry,
    ProviderSessionMode,
    ProviderSessionRequest,
)


def test_codex_default_model_and_cli_reasoning_key(tmp_path: Path) -> None:
    registry = ProviderRegistry()
    executor = ProviderExecutor(tmp_path, registry)

    default, error = executor.prepare_invocation(
        "codex", ProviderParams(), {}, "prompt"
    )
    overridden, override_error = executor.prepare_invocation(
        "codex",
        ProviderParams(),
        {},
        "prompt",
        provider_call_policy={"model": "explicit-model", "effort": "medium"},
    )

    assert error is override_error is None
    assert default is not None
    assert overridden is not None
    assert default.command[default.command.index("--model") + 1] == "gpt-5.5"
    assert default.command[default.command.index("--config") + 1] == (
        "model_reasoning_effort=high"
    )
    assert overridden.command[overridden.command.index("--model") + 1] == (
        "explicit-model"
    )
    assert overridden.command[overridden.command.index("--config") + 1] == (
        "model_reasoning_effort=medium"
    )


@pytest.mark.parametrize(
    "provider_name",
    (
        "codex",
        "codex_gpt55",
        "codex_unrestricted_workspace",
        "codex_gpt55_unrestricted_workspace",
    ),
)
def test_codex_command_profiles_use_cli_config_key(
    tmp_path: Path,
    provider_name: str,
) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation, error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        "prompt",
        provider_call_policy={"model": "chosen-model", "effort": "medium"},
    )

    assert error is None
    assert invocation is not None
    assert "model_reasoning_effort=medium" in invocation.command


@pytest.mark.parametrize(
    ("provider_name", "session_mode"),
    (
        ("codex", ProviderSessionMode.FRESH),
        ("codex", ProviderSessionMode.RESUME),
        ("codex_gpt55", ProviderSessionMode.FRESH),
        ("codex_gpt55", ProviderSessionMode.RESUME),
    ),
)
def test_codex_session_commands_use_cli_config_key(
    tmp_path: Path,
    provider_name: str,
    session_mode: ProviderSessionMode,
) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation, error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        "prompt",
        session_request=ProviderSessionRequest(
            mode=session_mode,
            session_id="session-id" if session_mode == ProviderSessionMode.RESUME else None,
        ),
        provider_call_policy={"model": "chosen-model", "effort": "medium"},
    )

    assert error is None
    assert invocation is not None
    assert "model_reasoning_effort=medium" in invocation.command


def test_codex_interactive_command_uses_cli_config_key(tmp_path: Path) -> None:
    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    invocation, error = executor.prepare_interactive_invocation(
        provider_name="codex",
        params={},
        context={},
        prompt_content="turn",
        invocation_id="invocation",
        member_id="worker",
        attempt_scope_key="sha256:" + "a" * 64,
        attempt_ordinal=1,
        cwd=tmp_path,
        provider_call_policy={"model": "chosen-model", "effort": "medium"},
    )

    assert error is None
    assert invocation is not None
    assert "model_reasoning_effort=medium" in invocation.pre_prompt_command
