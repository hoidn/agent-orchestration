"""Structural provider capability tests for interactive terminal sessions."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import orchestrator.providers as provider_api
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
