"""Provider-template call-policy binding contracts."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

import orchestrator.providers as providers
from orchestrator.providers import (
    CallPolicyBinding,
    InputMode,
    ProviderExecutor,
    ProviderParams,
    ProviderRegistry,
    ProviderSessionMode,
    ProviderSessionMetadataMode,
    ProviderSessionRequest,
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


def _executor(tmp_path) -> tuple[ProviderExecutor, ProviderRegistry]:
    registry = ProviderRegistry()
    return ProviderExecutor(tmp_path, registry), registry


def test_call_policy_merge_precedence_and_one_pass_substitution(
    tmp_path,
    monkeypatch,
) -> None:
    executor, registry = _executor(tmp_path)
    registry.register(
        ProviderTemplate(
            name="merge-policy",
            command=["tool", "${model}", "${reasoning_effort}", "${keep}"],
            defaults={"model": "default", "reasoning_effort": "low", "keep": "default-keep"},
            input_mode=InputMode.STDIN,
            call_policy_bindings={
                "model": CallPolicyBinding(target_param="model"),
                "effort": CallPolicyBinding(target_param="reasoning_effort"),
            },
        )
    )
    calls: list[dict[str, object]] = []
    original = executor._substitute_params

    def recording_substitute(params, context):
        calls.append(dict(params))
        return original(params, context)

    monkeypatch.setattr(executor, "_substitute_params", recording_substitute)

    invocation, error = executor.prepare_invocation(
        "merge-policy",
        ProviderParams(
            params={
                "model": "native-model",
                "reasoning_effort": "native-effort",
                "keep": "${inputs.keep}",
            }
        ),
        {
            "inputs": {
                "keep": "preserved",
                "model": "policy-model",
                "effort": "high",
            },
            "inputs.keep": "preserved",
            "inputs.model": "policy-model",
            "inputs.effort": "high",
        },
        provider_call_policy={
            "effort": "${inputs.effort}",
            "model": "${inputs.model}",
        },
    )

    assert error is None
    assert invocation is not None
    assert calls == [
        {
            "model": "${inputs.model}",
            "reasoning_effort": "${inputs.effort}",
            "keep": "${inputs.keep}",
        }
    ]
    assert invocation.command == ["tool", "policy-model", "high", "preserved"]


def test_call_policy_unresolved_dynamic_value_uses_single_substitution_error(
    tmp_path,
    monkeypatch,
) -> None:
    executor, _ = _executor(tmp_path)
    calls = 0
    original = executor._substitute_params

    def recording_substitute(params, context):
        nonlocal calls
        calls += 1
        return original(params, context)

    monkeypatch.setattr(executor, "_substitute_params", recording_substitute)

    invocation, error = executor.prepare_invocation(
        "codex",
        ProviderParams(),
        {},
        provider_call_policy={"model": "${inputs.missing}"},
    )

    assert invocation is None
    assert calls == 1
    assert error == {
        "type": "substitution_error",
        "message": "Failed to substitute provider parameters",
        "context": {
            "errors": ["Undefined variable in provider_params: ${inputs.missing}"]
        },
    }


def test_build_command_uses_shared_general_placeholder_extractor(
    tmp_path,
    monkeypatch,
) -> None:
    import orchestrator.providers.executor as executor_module

    executor, registry = _executor(tmp_path)
    registry.register(
        ProviderTemplate(
            name="dotted-placeholder-provider",
            command=[
                "tool",
                "${run.id}",
                "${context.workspace}",
                "${loop.item}",
                "${steps.prepare.output}",
                "$${literal}",
            ],
            input_mode=InputMode.STDIN,
        )
    )
    seen: list[str] = []
    original = extract_provider_command_placeholders

    def recording_extract(token: str):
        seen.append(token)
        return original(token)

    monkeypatch.setattr(
        executor_module,
        "extract_provider_command_placeholders",
        recording_extract,
    )
    context = {
        "run.id": "run-7",
        "context.workspace": "/workspace",
        "loop.item": "row-3",
        "steps.prepare.output": "ready",
    }

    invocation, error = executor.prepare_invocation(
        "dotted-placeholder-provider", ProviderParams(), context
    )

    assert error is None
    assert invocation is not None
    assert invocation.command == [
        "tool",
        "run-7",
        "/workspace",
        "row-3",
        "ready",
        "${literal}",
    ]
    assert seen == registry.get("dotted-placeholder-provider").command


@pytest.mark.parametrize(
    ("session_request", "expected_variant", "expected_prefix"),
    [
        (None, "command", ["codex", "exec"]),
        (
            ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
            "fresh_command",
            ["codex", "exec", "--json"],
        ),
        (
            ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id="session-9"),
            "resume_command",
            ["codex", "exec", "resume", "session-9", "--json"],
        ),
    ],
)
def test_codex_policy_maps_model_and_effort_on_actual_command_variant(
    tmp_path,
    session_request,
    expected_variant,
    expected_prefix,
) -> None:
    executor, _ = _executor(tmp_path)

    invocation, error = executor.prepare_invocation(
        "codex",
        ProviderParams(),
        {},
        session_request=session_request,
        provider_call_policy={"effort": "medium", "model": "gpt-policy"},
    )

    assert error is None
    assert invocation is not None
    assert invocation.command_variant == expected_variant
    assert invocation.command[: len(expected_prefix)] == expected_prefix
    assert invocation.command[invocation.command.index("--model") + 1] == "gpt-policy"
    assert "reasoning_effort=medium" in invocation.command


@pytest.mark.parametrize(
    "provider_name",
    ["claude", "claude_sonnet_summary", "claude_haiku_summary"],
)
def test_claude_policy_appends_effort_only_when_authored(
    tmp_path,
    provider_name,
) -> None:
    executor, _ = _executor(tmp_path)

    with_effort, with_error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        prompt_content="prompt",
        provider_call_policy={"model": "claude-policy", "effort": "high"},
    )
    without_effort, without_error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        prompt_content="prompt",
        provider_call_policy={"model": "claude-policy"},
    )

    assert with_error is without_error is None
    assert with_effort is not None
    assert without_effort is not None
    assert with_effort.command[-2:] == ["--effort", "high"]
    assert "--effort" not in without_effort.command


@pytest.mark.parametrize(
    ("provider_name", "policy", "expected"),
    [
        (
            "codex_unrestricted_workspace",
            {"model": "gpt-policy", "effort": "medium"},
            ["--model", "gpt-policy", "--config", "reasoning_effort=medium"],
        ),
        (
            "claude_unrestricted_workspace",
            {"model": "claude-policy", "effort": "high"},
            ["--model", "claude-policy", "--effort", "high"],
        ),
    ],
)
def test_no_default_profiles_consume_call_policy(
    tmp_path,
    provider_name,
    policy,
    expected,
) -> None:
    executor, _ = _executor(tmp_path)

    invocation, error = executor.prepare_invocation(
        provider_name,
        ProviderParams(),
        {},
        provider_call_policy=policy,
    )

    assert error is None
    assert invocation is not None
    joined = "\0".join(invocation.command)
    assert "\0".join(expected) in joined


@pytest.mark.parametrize(
    ("session_request", "expected_variant"),
    [
        (None, "command"),
        (ProviderSessionRequest(mode=ProviderSessionMode.FRESH), "fresh_command"),
        (
            ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id="custom-session"),
            "resume_command",
        ),
    ],
)
def test_custom_fragment_provider_applies_policy_to_selected_variant(
    tmp_path,
    session_request,
    expected_variant,
) -> None:
    executor, registry = _executor(tmp_path)
    registry.register(
        ProviderTemplate(
            name="custom-fragment",
            command=["tool", "base"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "fresh"],
                resume_command=["tool", "resume", "${SESSION_ID}"],
            ),
            call_policy_bindings={
                "effort": CallPolicyBinding(
                    target_param="native_effort",
                    argv_fragment=["--native-effort", "${native_effort}"],
                )
            },
        )
    )

    invocation, error = executor.prepare_invocation(
        "custom-fragment",
        ProviderParams(),
        {},
        session_request=session_request,
        provider_call_policy={"effort": "focused"},
    )

    assert error is None
    assert invocation is not None
    assert invocation.command_variant == expected_variant
    assert invocation.command[-2:] == ["--native-effort", "focused"]


def test_policy_fragments_append_in_canonical_order_not_declaration_order(
    tmp_path,
) -> None:
    executor, registry = _executor(tmp_path)
    registry.register(
        ProviderTemplate(
            name="reverse-fragments",
            command=["tool"],
            input_mode=InputMode.STDIN,
            call_policy_bindings={
                "effort": CallPolicyBinding(
                    target_param="native_effort",
                    argv_fragment=["--effort", "${native_effort}"],
                ),
                "model": CallPolicyBinding(
                    target_param="native_model",
                    argv_fragment=["--model", "${native_model}"],
                ),
            },
        )
    )

    invocation, error = executor.prepare_invocation(
        "reverse-fragments",
        ProviderParams(),
        {},
        provider_call_policy={"effort": "high", "model": "m"},
    )

    assert error is None
    assert invocation is not None
    assert invocation.command == ["tool", "--model", "m", "--effort", "high"]


def test_unsupported_call_policy_has_bounded_context_and_no_invocation(
    tmp_path,
) -> None:
    executor, _ = _executor(tmp_path)

    invocation, error = executor.prepare_invocation(
        "gemini",
        ProviderParams(),
        {},
        prompt_content="secret prompt",
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        provider_call_policy={"effort": "secret value"},
    )

    assert invocation is None
    assert error == {
        "type": "provider_call_policy_unsupported",
        "message": "Provider call policy option is not supported",
        "context": {"provider": "gemini", "option": "effort"},
    }
    serialized = repr(error)
    for forbidden in ("secret value", "secret prompt", "step", "span", "form"):
        assert forbidden not in serialized
