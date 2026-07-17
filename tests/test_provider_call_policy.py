"""Provider-template call-policy binding contracts."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

import orchestrator.providers as providers
from orchestrator.providers import (
    CallPolicyBinding,
    InputMode,
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionSupport,
    ProviderTemplate,
)
from orchestrator.providers.types import (
    CALL_POLICY_OPTION_ORDER,
    extract_provider_command_placeholders,
)


def _template(
    *,
    command: list[str] | None = None,
    bindings: Mapping[str, CallPolicyBinding] | None = None,
    fresh_command: list[str] | None = None,
    resume_command: list[str] | None = None,
) -> ProviderTemplate:
    session_support = None
    if fresh_command is not None or resume_command is not None:
        session_support = ProviderSessionSupport(
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            fresh_command=fresh_command or ["tool", "--fresh"],
            resume_command=resume_command,
        )
    return ProviderTemplate(
        name="custom",
        command=command or ["tool", "--model", "${model}"],
        input_mode=InputMode.STDIN,
        session_support=session_support,
        call_policy_bindings=bindings or {},
    )


def _binding_errors(template: ProviderTemplate) -> str:
    return "\n".join(template.validate())


def test_general_placeholder_extractor_preserves_provider_and_runtime_names_after_escapes() -> None:
    token = (
        "${model}:${run.id}:${context.workspace}:${loop.item}:"
        "${steps.prepare.output}:$${literal}:$$:${effort}"
    )

    assert extract_provider_command_placeholders(token) == (
        "model",
        "run.id",
        "context.workspace",
        "loop.item",
        "steps.prepare.output",
        "effort",
    )


@pytest.mark.parametrize("canonical_option", ["temperature", "MODEL", ""])
def test_binding_validation_rejects_unknown_canonical_keys(canonical_option: str) -> None:
    template = _template(
        bindings={canonical_option: CallPolicyBinding(target_param="model")}
    )

    assert "canonical" in _binding_errors(template)


@pytest.mark.parametrize(
    "target_param",
    [
        "",
        "two words",
        "run.id",
        "${model}",
        "model-name",
        "1model",
        "PROMPT",
        "SESSION_ID",
        "run",
        "context",
        "inputs",
        "loop",
        "item",
        "steps",
        "self",
        "parent",
        "root",
    ],
)
def test_binding_validation_rejects_invalid_or_reserved_target_param(
    target_param: str,
) -> None:
    template = _template(
        bindings={"model": CallPolicyBinding(target_param=target_param)}
    )

    assert "target_param" in _binding_errors(template)


def test_binding_validation_rejects_non_string_target_param() -> None:
    template = _template(
        bindings={"model": CallPolicyBinding(target_param=7)}  # type: ignore[arg-type]
    )

    assert "target_param" in _binding_errors(template)


def test_binding_validation_rejects_duplicate_native_targets() -> None:
    template = _template(
        bindings={
            "model": CallPolicyBinding(target_param="native"),
            "effort": CallPolicyBinding(target_param="native"),
        },
        command=["tool", "${native}"],
    )

    assert "unique" in _binding_errors(template)


@pytest.mark.parametrize(
    ("command", "fresh_command", "resume_command"),
    [
        (["tool"], ["tool", "${model}"], ["tool", "${SESSION_ID}", "${model}"]),
        (["tool", "${model}", "${model}"], ["tool", "${model}"], ["tool", "${SESSION_ID}", "${model}"]),
        (["tool", "${model}"], ["tool"], ["tool", "${SESSION_ID}", "${model}"]),
        (["tool", "${model}"], ["tool", "${model}"], ["tool", "${SESSION_ID}"]),
        (["tool", "${other}"], ["tool", "${model}"], ["tool", "${SESSION_ID}", "${model}"]),
    ],
)
def test_direct_binding_validation_requires_exactly_one_target_in_every_variant(
    command: list[str],
    fresh_command: list[str],
    resume_command: list[str],
) -> None:
    template = _template(
        command=command,
        fresh_command=fresh_command,
        resume_command=resume_command,
        bindings={"model": CallPolicyBinding(target_param="model")},
    )

    assert "exactly one" in _binding_errors(template)


def test_direct_binding_validation_ignores_escaped_target_placeholder() -> None:
    valid = _template(
        command=["tool", "$${model}", "${model}"],
        fresh_command=["tool", "$${model}", "${model}"],
        resume_command=["tool", "${SESSION_ID}", "$${model}", "${model}"],
        bindings={"model": CallPolicyBinding(target_param="model")},
    )
    invalid = _template(
        command=["tool", "$${model}"],
        bindings={"model": CallPolicyBinding(target_param="model")},
    )

    assert valid.validate() == []
    assert "exactly one" in _binding_errors(invalid)


@pytest.mark.parametrize(
    "fragment",
    [
        [],
        ["--effort"],
        ["--effort", "${other}"],
        ["--effort", "${effort}", "${effort}"],
        ["--effort", "${effort}", "${other}"],
        ["--effort", "${effort}", "${PROMPT}"],
        ["--effort", "${effort}", "${SESSION_ID}"],
        ["--effort", "${effort}", "${context.workspace}"],
        ["--effort", "$${effort}"],
    ],
)
def test_fragment_binding_validation_requires_one_exact_dynamic_target(
    fragment: list[str],
) -> None:
    template = _template(
        bindings={
            "effort": CallPolicyBinding(
                target_param="effort",
                argv_fragment=fragment,
            )
        }
    )

    assert "argv_fragment" in _binding_errors(template)


@pytest.mark.parametrize(
    "fragment",
    ["--effort ${effort}", ["--effort", 1], {"value": "${effort}"}],
)
def test_binding_validation_rejects_malformed_or_non_string_fragments(
    fragment: object,
) -> None:
    template = _template(
        bindings={
            "effort": CallPolicyBinding(
                target_param="effort",
                argv_fragment=fragment,  # type: ignore[arg-type]
            )
        }
    )

    assert "argv_fragment" in _binding_errors(template)


@pytest.mark.parametrize(
    ("command", "fresh_command", "resume_command"),
    [
        (["tool", "${effort}"], ["tool"], ["tool", "${SESSION_ID}"]),
        (["tool"], ["tool", "${effort}"], ["tool", "${SESSION_ID}"]),
        (["tool"], ["tool"], ["tool", "${SESSION_ID}", "${effort}"]),
    ],
)
def test_fragment_binding_validation_rejects_target_in_every_base_variant(
    command: list[str],
    fresh_command: list[str],
    resume_command: list[str],
) -> None:
    template = _template(
        command=command,
        fresh_command=fresh_command,
        resume_command=resume_command,
        bindings={
            "effort": CallPolicyBinding(
                target_param="effort",
                argv_fragment=["--effort", "${effort}"],
            )
        },
    )

    assert "must not contain" in _binding_errors(template)


def test_fragment_binding_validation_accepts_escaped_target_in_base_variants() -> None:
    template = _template(
        command=["tool", "$${effort}"],
        fresh_command=["tool", "$${effort}"],
        resume_command=["tool", "${SESSION_ID}", "$${effort}"],
        bindings={
            "effort": CallPolicyBinding(
                target_param="effort",
                argv_fragment=["--effort", "$${literal}", "${effort}"],
            )
        },
    )

    assert template.validate() == []


def test_public_call_policy_binding_constructs_custom_template() -> None:
    assert "CallPolicyBinding" in providers.__all__
    binding = CallPolicyBinding(
        target_param="effort",
        argv_fragment=["--effort", "${effort}"],
    )
    template = ProviderTemplate(
        name="custom_fragment_provider",
        command=["tool"],
        input_mode=InputMode.STDIN,
        call_policy_bindings={"effort": binding},
    )

    assert template.validate() == []
    registry = ProviderRegistry()
    registry.register(template)
    assert registry.get(template.name) is template
    assert registry.get(template.name).call_policy_bindings["effort"] is binding


def test_binding_schema_does_not_coerce_dicts_to_public_dataclass() -> None:
    template = ProviderTemplate(
        name="dict_binding",
        command=["tool", "${model}"],
        input_mode=InputMode.STDIN,
        call_policy_bindings={"model": {"target_param": "model"}},  # type: ignore[dict-item]
    )

    assert "CallPolicyBinding" in _binding_errors(template)


@pytest.mark.parametrize("malformed_variant", ["command", "fresh", "resume"])
def test_binding_validation_reports_malformed_command_containers_without_raising(
    malformed_variant: str,
) -> None:
    command: object = ["tool", "${model}"]
    fresh_command: object = ["tool", "${model}"]
    resume_command: object = ["tool", "${SESSION_ID}", "${model}"]
    if malformed_variant == "command":
        command = None
    elif malformed_variant == "fresh":
        fresh_command = None
    else:
        resume_command = {"not": "a command token list"}

    template = ProviderTemplate(
        name=f"malformed_{malformed_variant}",
        command=command,  # type: ignore[arg-type]
        input_mode=InputMode.STDIN,
        session_support=ProviderSessionSupport(
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            fresh_command=fresh_command,  # type: ignore[arg-type]
            resume_command=resume_command,  # type: ignore[arg-type]
        ),
        call_policy_bindings={
            "model": CallPolicyBinding(target_param="model")
        },
    )

    errors = template.validate()

    assert errors
    assert any("cannot be empty" in error for error in errors)
    registry = ProviderRegistry()
    with pytest.raises(ValueError, match=f"malformed_{malformed_variant}"):
        registry.register(template)


def test_call_policy_binding_copies_mutable_fragment_input() -> None:
    source_fragment = ["--effort", "${effort}"]
    binding = CallPolicyBinding(
        target_param="effort",
        argv_fragment=source_fragment,
    )
    template = ProviderTemplate(
        name="immutable_fragment",
        command=["tool"],
        input_mode=InputMode.STDIN,
        call_policy_bindings={"effort": binding},
    )
    registry = ProviderRegistry()
    registry.register(template)

    source_fragment.extend(["--other", "${other}"])

    registered = registry.get("immutable_fragment")
    assert registered is not None
    assert registered.call_policy_bindings["effort"].argv_fragment == (
        "--effort",
        "${effort}",
    )
    assert registered.validate() == []


def test_canonical_option_order_is_closed_and_stable() -> None:
    assert CALL_POLICY_OPTION_ORDER == ("model", "effort")


def test_provider_without_call_policy_declarations_remains_valid() -> None:
    template = ProviderTemplate(
        name="legacy",
        command=["tool", "${arbitrary}", "${context.workspace}"],
        input_mode=InputMode.STDIN,
    )

    assert template.validate() == []


@pytest.mark.parametrize("provider_name", ["codex", "codex_gpt55"])
def test_builtin_codex_call_policy_bindings(provider_name: str) -> None:
    provider = ProviderRegistry().get(provider_name)
    assert provider is not None
    assert provider.call_policy_bindings == {
        "model": CallPolicyBinding(target_param="model"),
        "effort": CallPolicyBinding(target_param="reasoning_effort"),
    }
    assert provider.validate() == []


@pytest.mark.parametrize(
    "provider_name",
    ["claude", "claude_sonnet_summary", "claude_haiku_summary"],
)
def test_builtin_claude_call_policy_bindings_are_conditional(
    provider_name: str,
) -> None:
    provider = ProviderRegistry().get(provider_name)
    assert provider is not None
    assert provider.call_policy_bindings == {
        "model": CallPolicyBinding(target_param="model"),
        "effort": CallPolicyBinding(
            target_param="effort",
            argv_fragment=["--effort", "${effort}"],
        ),
    }
    assert "${effort}" not in provider.command
    assert provider.validate() == []


def test_builtin_gemini_declares_no_call_policy_capability() -> None:
    provider = ProviderRegistry().get("gemini")
    assert provider is not None
    assert provider.call_policy_bindings == {}


def test_builtin_codex_unrestricted_workspace_is_no_default_direct_profile() -> None:
    provider = ProviderRegistry().get("codex_unrestricted_workspace")
    assert provider is not None
    assert provider.defaults == {}
    assert provider.input_mode == InputMode.STDIN
    assert provider.command == [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "${model}",
        "--config",
        "reasoning_effort=${reasoning_effort}",
    ]
    assert provider.call_policy_bindings == {
        "model": CallPolicyBinding(target_param="model"),
        "effort": CallPolicyBinding(target_param="reasoning_effort"),
    }
    assert provider.validate() == []


def test_builtin_claude_unrestricted_workspace_is_no_default_direct_profile() -> None:
    provider = ProviderRegistry().get("claude_unrestricted_workspace")
    assert provider is not None
    assert provider.defaults == {}
    assert provider.input_mode == InputMode.STDIN
    assert provider.command == [
        "claude",
        "-p",
        "--model",
        "${model}",
        "--effort",
        "${effort}",
        "--permission-mode",
        "bypassPermissions",
    ]
    assert provider.call_policy_bindings == {
        "model": CallPolicyBinding(target_param="model"),
        "effort": CallPolicyBinding(target_param="effort"),
    }
    assert provider.validate() == []
