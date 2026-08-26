"""
Tests for provider execution per specs/providers.md and acceptance tests.

Tests provider registry, template validation, argv/stdin modes, placeholder
substitution, and error handling.
"""

import pytest
import tempfile
import time
import threading
import os
import signal
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from orchestrator.providers import (
    ProviderTemplate,
    ProviderParams,
    ProviderRegistry,
    ProviderExecutor,
    ProviderExecutionResult,
    InputMode,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
    ProviderSessionSupport,
)
from orchestrator.providers.types import PreparedProviderPolicy, ProviderInvocation
from orchestrator.providers.control import ProviderExecutionControl
from orchestrator.workflow.provider_attempts import (
    PROVIDER_ATTEMPT_SITE_KEY_ENV,
)


class _TimeoutIntSubclass(int):
    pass


class _TimeoutFloatSubclass(float):
    pass


@pytest.mark.parametrize(
    ("timeout_sec", "accepted"),
    (
        (True, False),
        (False, False),
        (float("nan"), False),
        (float("inf"), False),
        (float("-inf"), False),
        (0, False),
        (-1, False),
        (1, True),
        (10**309, True),
        (0.25, True),
    ),
)
def test_prepared_provider_timeout_finite_positive_boundary_precedes_launch(
    timeout_sec: object,
    accepted: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launches: list[object] = []

    def unexpected_launch(*args, **kwargs):
        launches.append((args, kwargs))
        raise AssertionError("invalid prepared policy must not launch")

    monkeypatch.setattr(subprocess, "Popen", unexpected_launch)
    arguments = {
        "provider_name": "provider",
        "model": None,
        "effort": None,
        "timeout_sec": timeout_sec,
        "input_mode": InputMode.ARGV.value,
    }

    if accepted:
        policy = PreparedProviderPolicy(**arguments)
        assert policy.timeout_sec == timeout_sec
    else:
        with pytest.raises(
            ValueError,
            match=(
                "^prepared provider timeout must be finite "
                "positive seconds$"
            ),
        ):
            PreparedProviderPolicy(**arguments)

    assert launches == []


@pytest.mark.parametrize(
    "timeout_sec",
    (_TimeoutIntSubclass(1), _TimeoutFloatSubclass(0.25)),
)
def test_prepared_provider_timeout_preserves_exact_numeric_type_policy(
    timeout_sec: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="^prepared provider timeout must be finite positive seconds$",
    ):
        PreparedProviderPolicy(
            provider_name="provider",
            model=None,
            effort=None,
            timeout_sec=timeout_sec,
            input_mode=InputMode.ARGV.value,
        )


def test_turn_boundary_resume_capability_is_structural():
    """Live resume capability is an explicit, generic session contract."""

    def session_support(
        *,
        enabled=True,
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        fresh_command=None,
        resume_command=None,
    ):
        return ProviderSessionSupport(
            metadata_mode=metadata_mode,
            fresh_command=(
                ["tool", "--json", "--ephemeral=true"]
                if fresh_command is None
                else fresh_command
            ),
            resume_command=(
                [
                    "tool",
                    "resume",
                    "${SESSION_ID}",
                    "--json",
                    "--not-ephemeral",
                ]
                if resume_command is None
                else resume_command
            ),
            turn_boundary_resume=enabled,
        )

    def provider(support, *, name="structural-provider", input_mode=InputMode.ARGV):
        return ProviderTemplate(
            name=name,
            command=(
                ["tool", "--tty"]
                if input_mode == InputMode.STDIN
                else ["tool", "--tty", "${PROMPT}"]
            ),
            input_mode=input_mode,
            session_support=support,
        )

    capable = provider(session_support())

    assert capable.validate() == []
    assert capable.session_support is not None
    assert capable.session_support.turn_boundary_resume is True

    invalid_cases = (
        (
            session_support(fresh_command=[]),
            ("turn_boundary_resume", "fresh_command"),
        ),
        (
            session_support(resume_command=[]),
            ("turn_boundary_resume", "resume_command"),
        ),
        (
            session_support(resume_command=["tool", "resume"]),
            ("exactly one", "${SESSION_ID}"),
        ),
        (
            session_support(
                resume_command=[
                    "tool",
                    "resume",
                    "${SESSION_ID}",
                    "${SESSION_ID}",
                ],
            ),
            ("exactly one", "${SESSION_ID}"),
        ),
        (
            session_support(
                resume_command=["tool", "resume", "$${SESSION_ID}"],
            ),
            ("exactly one", "${SESSION_ID}"),
        ),
        (
            session_support(metadata_mode="identity-only-codec"),
            ("turn_boundary_resume", "resume-boundary"),
        ),
        (
            session_support(
                fresh_command=["tool", "--json", "--ephemeral"],
            ),
            ("turn_boundary_resume", "--ephemeral"),
        ),
        (
            session_support(
                resume_command=[
                    "tool",
                    "resume",
                    "${SESSION_ID}",
                    "--ephemeral",
                ],
            ),
            ("turn_boundary_resume", "--ephemeral"),
        ),
    )

    for support, expected_fragments in invalid_cases:
        errors = provider(support).validate()
        assert any(
            all(fragment in error for fragment in expected_fragments)
            for error in errors
        ), errors

    inferred = provider(
        session_support(enabled=False),
        name="codex",
        input_mode=InputMode.STDIN,
    )

    assert inferred.validate() == []
    assert inferred.session_support is not None
    assert inferred.session_support.turn_boundary_resume is False


def test_provider_supervision_worker_runtime_repeats_capability_and_control_gate(
    tmp_path,
    monkeypatch,
):
    """A live worker cannot reach either provider execution path by inference."""

    registry = ProviderRegistry()
    executor = ProviderExecutor(tmp_path, registry)
    controlled_calls = []
    uncontrolled_calls = []
    success = ProviderExecutionResult(
        exit_code=0,
        stdout=b"",
        stderr=b"",
        duration_ms=0,
    )

    def controlled(**kwargs):
        controlled_calls.append(kwargs["invocation"])
        return success

    def uncontrolled(**kwargs):
        uncontrolled_calls.append(kwargs["invocation"])
        return success

    monkeypatch.setattr(
        executor,
        "_execute_controlled_invocation",
        controlled,
    )
    monkeypatch.setattr(
        executor,
        "_execute_session_invocation",
        uncontrolled,
    )

    def prepared_worker(provider_name):
        invocation, error = executor.prepare_invocation(
            provider_name,
            ProviderParams(),
            {},
            "work",
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.FRESH,
            ),
        )
        assert error is None
        assert invocation is not None
        invocation.metadata["provider_supervision"] = {
            "member_id": "worker",
            "turn_role": "worker_fresh",
        }
        return invocation

    capable = prepared_worker("codex")
    unsupported_alias = prepared_worker("codex_gpt55")

    assert executor.execute(
        capable,
        control=ProviderExecutionControl(),
    ) is success
    assert controlled_calls == [capable]
    assert uncontrolled_calls == []

    unsupported_result = executor.execute(
        unsupported_alias,
        control=ProviderExecutionControl(),
    )
    assert unsupported_result.is_promotable is False
    assert "turn_boundary_resume" in str(unsupported_result.error)
    assert controlled_calls == [capable]
    assert uncontrolled_calls == []

    missing_control_result = executor.execute(capable)
    assert missing_control_result.is_promotable is False
    assert "cancellable" in str(missing_control_result.error)
    assert controlled_calls == [capable]
    assert uncontrolled_calls == []


class _RecordingBinaryStream:
    """Thread-safe binary stream recorder for live provider streaming assertions."""

    def __init__(self):
        self.buffer = self
        self._chunks = []
        self._lock = threading.Lock()
        self.first_write_at = None

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        with self._lock:
            if self.first_write_at is None:
                self.first_write_at = time.time()
            self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        return None

    def getvalue(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)


class TestProviderRegistry:
    """Test provider registry functionality."""

    def test_builtin_providers(self):
        """Test that built-in providers are available."""
        registry = ProviderRegistry()

        # Check built-in providers exist
        assert registry.exists("claude")
        assert registry.exists("gemini")
        assert registry.exists("codex")

        # Check claude template
        claude = registry.get("claude")
        assert claude.name == "claude"
        assert claude.input_mode == InputMode.ARGV
        assert "${PROMPT}" in " ".join(claude.command)
        assert claude.defaults.get("model") == "claude-opus-4-6"

        # Check codex template (stdin mode)
        codex = registry.get("codex")
        assert codex.name == "codex"
        assert codex.input_mode == InputMode.STDIN
        assert "${PROMPT}" not in " ".join(codex.command)
        assert codex.defaults.get("model") == "gpt-5.4"
        assert codex.defaults.get("reasoning_effort") == "high"
        command_str = " ".join(codex.command)
        assert "--config" in command_str
        assert "reasoning_effort=${reasoning_effort}" in command_str
        assert codex.session_support is not None
        assert codex.session_support.metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        assert "${SESSION_ID}" in " ".join(codex.session_support.resume_command or [])

    def test_builtin_codex_gpt55_provider_alias(self):
        """Test workflow-scoped callers can opt into GPT-5.5 without changing codex default."""
        registry = ProviderRegistry()

        codex = registry.get("codex")
        codex_gpt55 = registry.get("codex_gpt55")

        assert codex is not None
        assert codex_gpt55 is not None
        assert codex.defaults.get("model") == "gpt-5.4"
        assert codex_gpt55.name == "codex_gpt55"
        assert codex_gpt55.input_mode == InputMode.STDIN
        assert codex_gpt55.defaults.get("model") == "gpt-5.5"
        assert codex_gpt55.defaults.get("reasoning_effort") == "high"
        assert "${PROMPT}" not in " ".join(codex_gpt55.command)
        assert codex_gpt55.session_support is not None
        assert codex_gpt55.session_support.metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value

    def test_register_custom_provider(self):
        """Test registering a custom provider."""
        registry = ProviderRegistry()

        custom = ProviderTemplate(
            name="custom",
            command=["custom-cli", "--prompt", "${PROMPT}"],
            defaults={"timeout": "30"},
            input_mode=InputMode.ARGV
        )

        registry.register(custom)
        assert registry.exists("custom")

        retrieved = registry.get("custom")
        assert retrieved.name == "custom"
        assert retrieved.defaults["timeout"] == "30"

    def test_invalid_monkeypatched_builtin_fails_registry_initialization(
        self,
        monkeypatch,
    ):
        """Built-ins pass the same validation boundary as custom templates."""
        def invalid_builtins(_registry):
            return {
                "invalid_builtin": ProviderTemplate(
                    name="invalid_builtin",
                    command=[],
                    input_mode=InputMode.STDIN,
                )
            }

        monkeypatch.setattr(
            ProviderRegistry,
            "_load_builtin_providers",
            invalid_builtins,
        )

        with pytest.raises(ValueError, match="invalid_builtin"):
            ProviderRegistry()

    def test_at49_stdin_mode_prompt_validation(self):
        """AT-49: Provider with stdin mode cannot have ${PROMPT} in command."""
        registry = ProviderRegistry()

        # Invalid: stdin mode with ${PROMPT}
        invalid = ProviderTemplate(
            name="invalid",
            command=["tool", "-p", "${PROMPT}"],  # Not allowed in stdin
            input_mode=InputMode.STDIN
        )

        errors = invalid.validate()
        assert len(errors) > 0
        assert "${PROMPT} not allowed in stdin mode" in errors[0]

    def test_session_support_resume_command_requires_exactly_one_session_placeholder(self):
        """Resume-capable provider templates must bind exactly one ${SESSION_ID}."""
        invalid = ProviderTemplate(
            name="invalid_resume",
            command=["tool", "--model", "${model}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "--model", "${model}"],
                resume_command=["tool", "resume", "--model", "${model}"],
            ),
        )

        errors = invalid.validate()

        assert any("must contain exactly one ${SESSION_ID} placeholder" in error for error in errors)

    def test_session_support_resume_command_ignores_escaped_session_placeholder(self):
        """Escaped ${SESSION_ID} literals do not satisfy the reserved resume placeholder contract."""
        escaped_only = ProviderTemplate(
            name="escaped_only_resume",
            command=["tool", "--model", "${model}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "--model", "${model}"],
                resume_command=["tool", "resume", "$${SESSION_ID}"],
            ),
        )

        escaped_only_errors = escaped_only.validate()

        assert any(
            "must contain exactly one ${SESSION_ID} placeholder" in error
            for error in escaped_only_errors
        )

        one_real_one_escaped = ProviderTemplate(
            name="resume_with_literal",
            command=["tool", "--model", "${model}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "--model", "${model}"],
                resume_command=["tool", "resume", "$${SESSION_ID}", "${SESSION_ID}"],
            ),
        )

        assert one_real_one_escaped.validate() == []

    def test_session_id_placeholder_is_reserved_for_resume_command(self):
        """${SESSION_ID} is rejected outside session_support.resume_command."""
        invalid = ProviderTemplate(
            name="invalid_placeholder_scope",
            command=["tool", "resume", "${SESSION_ID}"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json", "${SESSION_ID}"],
                resume_command=["tool", "resume", "${SESSION_ID}"],
            ),
        )

        errors = invalid.validate()

        assert any("${SESSION_ID} is only allowed in session_support.resume_command" in error for error in errors)

    def test_merge_params(self):
        """Test parameter merging (step params override defaults)."""
        registry = ProviderRegistry()

        # Get claude with defaults
        defaults = registry.merge_params("claude", None)
        assert defaults["model"] == "claude-opus-4-6"

        # Override with step params
        step_params = {"model": "claude-3-5-sonnet"}
        merged = registry.merge_params("claude", step_params)
        assert merged["model"] == "claude-3-5-sonnet"  # Step wins

        # Additional params
        step_params = {"model": "custom", "temperature": "0.7"}
        merged = registry.merge_params("claude", step_params)
        assert merged["model"] == "custom"
        assert merged["temperature"] == "0.7"


class TestProviderExecutor:
    """Test provider executor functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.registry = ProviderRegistry()
        self.executor = ProviderExecutor(self.workspace, self.registry)

    def test_at8_argv_mode_execution(self):
        """AT-8: Provider templates with argv mode compose correctly."""
        # Create a test prompt file
        prompt_file = self.workspace / "prompt.txt"
        prompt_file.write_text("Test prompt content")

        params = ProviderParams(
            params={"model": "test-model"},
            input_file=str(prompt_file)
        )

        context = {}
        prompt_content = "Test prompt content"

        # Prepare invocation for claude (argv mode)
        invocation, error = self.executor.prepare_invocation(
            "claude",
            params,
            context,
            prompt_content
        )

        assert error is None
        assert invocation is not None
        assert invocation.input_mode == InputMode.ARGV

        # Check command has prompt substituted
        command_str = " ".join(invocation.command)
        assert "Test prompt content" in command_str
        assert "test-model" in command_str

    def test_at9_stdin_mode_execution(self):
        """AT-9: Provider with stdin mode receives prompt via stdin."""
        params = ProviderParams(
            params={"model": "test-model"}
        )

        context = {}
        prompt_content = "Test prompt for stdin"

        # Prepare invocation for codex (stdin mode)
        invocation, error = self.executor.prepare_invocation(
            "codex",
            params,
            context,
            prompt_content
        )

        assert error is None
        assert invocation is not None
        assert invocation.input_mode == InputMode.STDIN
        assert invocation.prompt == "Test prompt for stdin"

        # Command should not have ${PROMPT}
        command_str = " ".join(invocation.command)
        assert "${PROMPT}" not in command_str
        assert "test-model" in command_str

    @pytest.mark.parametrize("controlled", (False, True))
    def test_execution_env_overlay_reaches_only_the_subprocess_and_wins(
        self,
        controlled: bool,
    ) -> None:
        authored = "sha256:" + "a" * 64
        runtime_owned = "sha256:" + "b" * 64
        invocation = ProviderInvocation(
            command=[
                sys.executable,
                "-c",
                (
                    "import os,sys;sys.stdout.write("
                    f"os.environ[{PROVIDER_ATTEMPT_SITE_KEY_ENV!r}]"
                    ")"
                ),
            ],
            input_mode=InputMode.ARGV,
            env={PROVIDER_ATTEMPT_SITE_KEY_ENV: authored},
        )

        result = self.executor.execute(
            invocation,
            control=ProviderExecutionControl() if controlled else None,
            execution_env_overlay={
                PROVIDER_ATTEMPT_SITE_KEY_ENV: runtime_owned,
            },
        )

        assert result.exit_code == 0
        assert result.stdout.decode("ascii") == runtime_owned
        assert invocation.env == {PROVIDER_ATTEMPT_SITE_KEY_ENV: authored}

    def test_absent_execution_env_overlay_preserves_ordinary_environment(
        self,
    ) -> None:
        invocation = ProviderInvocation(
            command=[
                sys.executable,
                "-c",
                "import os,sys;sys.stdout.write(os.environ['ORDINARY_ENV'])",
            ],
            input_mode=InputMode.ARGV,
            env={"ORDINARY_ENV": "ordinary"},
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"ordinary"

    @pytest.mark.parametrize(
        ("overlay", "message"),
        (
            ([], "execution_env_overlay must be an exact dict or None"),
            ({1: "value"}, "execution_env_overlay keys must be strings"),
            ({"KEY": 1}, "execution_env_overlay values must be strings"),
            ({"": "value"}, "execution_env_overlay key is invalid"),
            ({"BAD=KEY": "value"}, "execution_env_overlay key is invalid"),
            ({"KEY": "bad\0value"}, "execution_env_overlay value is invalid"),
        ),
    )
    def test_execution_env_overlay_fails_closed_on_invalid_shape(
        self,
        overlay: object,
        message: str,
    ) -> None:
        invocation = ProviderInvocation(
            command=[sys.executable, "-c", "raise SystemExit(99)"],
            input_mode=InputMode.ARGV,
        )

        with pytest.raises((TypeError, ValueError), match=f"^{message}$"):
            self.executor.execute(  # pyright: ignore[reportArgumentType]
                invocation,
                execution_env_overlay=overlay,  # pyright: ignore[reportArgumentType]
            )

    def test_policy_absence_preserves_native_codex_and_keyword_free_claude_argv(self):
        default_codex, default_error = self.executor.prepare_invocation(
            "codex", ProviderParams(), {}, "prompt"
        )
        overridden_codex, overridden_error = self.executor.prepare_invocation(
            "codex",
            ProviderParams(params={"reasoning_effort": "medium"}),
            {},
            "prompt",
        )
        claude, claude_error = self.executor.prepare_invocation(
            "claude", ProviderParams(), {}, "prompt"
        )

        assert default_error is overridden_error is claude_error is None
        assert default_codex is not None
        assert overridden_codex is not None
        assert claude is not None
        assert "reasoning_effort=high" in default_codex.command
        assert "reasoning_effort=medium" in overridden_codex.command
        assert "--effort" not in claude.command

    def test_runtime_delivery_policy_never_enters_native_params_or_argv(self):
        invocation, error = self.executor.prepare_invocation(
            "codex",
            ProviderParams(),
            {},
            "prompt",
            provider_call_policy={
                "model": "policy-model",
                "effort": "medium",
                "delivery": "phased",
                "materialization_attempts": 3,
            },
        )

        assert error is None
        assert invocation is not None
        assert invocation.command[:6] == [
            "codex",
            "exec",
            "--model",
            "policy-model",
            "--config",
            "reasoning_effort=medium",
        ]
        assert invocation.prepared_provider_policy is not None
        assert invocation.prepared_provider_policy.model == "policy-model"
        assert invocation.prepared_provider_policy.effort == "medium"
        assert all("phased" not in token for token in invocation.command)
        assert all("materialization" not in token for token in invocation.command)

    def test_unknown_mixed_policy_key_fails_at_shared_partition(self):
        invocation, error = self.executor.prepare_invocation(
            "codex",
            ProviderParams(),
            {},
            "prompt",
            provider_call_policy={
                "delivery": "phased",
                "materialization_attempts": 2,
                "future_runtime_key": "closed",
            },
        )

        assert invocation is None
        assert error == {
            "type": "provider_call_policy_unsupported",
            "message": "Provider call policy option is not supported",
            "context": {
                "provider": "codex",
                "option": "future_runtime_key",
            },
        }

    def test_yaml_local_provider_params_keep_native_and_unused_compatibility(self):
        errors = self.registry.register_from_workflow(
            {
                "yaml-local": {
                    "command": ["tool", "${model}", "$${literal}"],
                    "defaults": {"model": "default"},
                    "input_mode": "stdin",
                }
            }
        )

        invocation, error = self.executor.prepare_invocation(
            "yaml-local",
            ProviderParams(
                params={"model": "native", "unused_compatibility": "retained"}
            ),
            {},
        )

        assert errors == []
        assert error is None
        assert invocation is not None
        assert invocation.command == ["tool", "native", "${literal}"]

    def test_managed_invocation_timeout_terminates_process_tree(self):
        """Managed provider timeout kills the guard process group, including children."""
        pid_file = self.workspace / "child.pid"
        script = self.workspace / "spawn_child.py"
        script.write_text(
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        invocation = ProviderInvocation(
            command=[sys.executable, str(script)],
            input_mode=InputMode.ARGV,
            timeout_sec=1,
            terminate_process_tree=True,
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 124
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("child process survived managed provider timeout")

    def test_at48_missing_placeholders(self):
        """AT-48: Missing placeholders cause exit 2 with context."""
        # Register a provider with unresolved placeholder
        custom = ProviderTemplate(
            name="custom",
            command=["tool", "--model", "${model}", "--key", "${api_key}"],
            input_mode=InputMode.ARGV
        )
        self.registry.register(custom)

        params = ProviderParams(
            params={"model": "test"}  # Missing api_key
        )

        context = {}

        invocation, error = self.executor.prepare_invocation(
            "custom",
            params,
            context,
            None
        )

        assert invocation is None
        assert error is not None
        assert error["type"] == "validation_error"
        assert "missing_placeholders" in error["context"]
        assert "api_key" in error["context"]["missing_placeholders"]

    def test_at49_invalid_prompt_placeholder(self):
        """AT-49: stdin mode with ${PROMPT} causes validation error."""
        # Register invalid provider
        invalid = ProviderTemplate(
            name="invalid",
            command=["tool", "-p", "${PROMPT}"],
            input_mode=InputMode.STDIN
        )

        # Note: This should fail at registration
        errors = invalid.validate()
        assert len(errors) > 0

        # Even if we bypass validation, executor should catch it
        self.registry._providers["invalid"] = invalid  # Force registration

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "invalid",
            params,
            context,
            "prompt"
        )

        assert invocation is None
        assert error is not None
        assert error["context"]["invalid_prompt_placeholder"] is True

    def test_at50_argv_without_prompt(self):
        """AT-50: Provider argv mode without ${PROMPT} runs without prompt."""
        # Register provider without ${PROMPT}
        no_prompt = ProviderTemplate(
            name="no_prompt",
            command=["tool", "--model", "${model}"],
            defaults={"model": "default"},
            input_mode=InputMode.ARGV
        )
        self.registry.register(no_prompt)

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "no_prompt",
            params,
            context,
            None  # No prompt
        )

        assert error is None
        assert invocation is not None
        assert "--model" in invocation.command
        assert "default" in invocation.command

    def test_at51_provider_params_substitution(self):
        """AT-51: Variable substitution in provider_params."""
        # Register provider
        custom = ProviderTemplate(
            name="custom",
            command=["tool", "--model", "${model}", "--path", "${output_path}"],
            input_mode=InputMode.ARGV
        )
        self.registry.register(custom)

        params = ProviderParams(
            params={
                "model": "${run.timestamp}",  # Variable reference
                "output_path": "${context.workspace}/output.txt"
            }
        )

        # Properly structured context with namespaces
        context = {
            "run": {
                "timestamp": "20250115T120000Z"
            },
            "context": {
                "workspace": "/workspace"
            }
        }

        invocation, error = self.executor.prepare_invocation(
            "custom",
            params,
            context,
            None
        )

        assert error is None
        assert invocation is not None

        # Check substitution worked
        command_str = " ".join(invocation.command)
        assert "20250115T120000Z" in command_str
        assert "/workspace/output.txt" in command_str

    def test_provider_param_substitution_retains_missing_values_across_mapping_entries(self):
        """One merged parameter pass must not lose an earlier missing variable."""
        substituted, errors = self.executor._substitute_params(
            {
                "missing": "${inputs.missing}",
                "resolved": "${inputs.present}",
            },
            {"inputs": {"present": "ok"}},
        )

        assert substituted == {
            "missing": "${inputs.missing}",
            "resolved": "ok",
        }
        assert errors == [
            "Undefined variable in provider_params: ${inputs.missing}"
        ]

    def test_prepare_invocation_uses_fresh_command_for_provider_session(self):
        """Session-enabled fresh invocations compile the provider fresh_command variant."""
        params = ProviderParams(params={"model": "test-model"})
        invocation, error = self.executor.prepare_invocation(
            "codex",
            params,
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        assert error is None
        assert invocation is not None
        assert invocation.command_variant == "fresh_command"
        assert invocation.metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        assert "--json" in invocation.command

    def test_prepare_invocation_uses_resume_command_and_binds_session_id(self):
        """Session-enabled resume invocations bind ${SESSION_ID} through resume_command only."""
        params = ProviderParams(params={"model": "test-model"})
        invocation, error = self.executor.prepare_invocation(
            "codex",
            params,
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
        )

        assert error is None
        assert invocation is not None
        assert invocation.command_variant == "resume_command"
        assert "resume" in invocation.command
        assert "sess-123" in invocation.command

    def test_provider_session_preserves_runtime_output_bundle_env(self):
        """Session command selection preserves the runtime-owned bundle env binding."""
        env = {
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": "state/runtime-owned/bundle.json",
            "EXISTING": "1",
        }

        fresh_invocation, fresh_error = self.executor.prepare_invocation(
            "codex",
            ProviderParams(),
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
            env=env,
        )
        resume_invocation, resume_error = self.executor.prepare_invocation(
            "codex",
            ProviderParams(),
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
            env=env,
        )

        assert fresh_error is None
        assert fresh_invocation is not None
        assert fresh_invocation.command_variant == "fresh_command"
        assert fresh_invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        assert fresh_invocation.env["EXISTING"] == "1"

        assert resume_error is None
        assert resume_invocation is not None
        assert resume_invocation.command_variant == "resume_command"
        assert resume_invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        assert resume_invocation.env["EXISTING"] == "1"

    def test_prepare_invocation_preserves_escaped_session_id_literal(self):
        """Escaped ${SESSION_ID} tokens remain literal while the unescaped token is bound."""
        custom = ProviderTemplate(
            name="custom_session",
            command=["tool"],
            input_mode=InputMode.STDIN,
            session_support=ProviderSessionSupport(
                metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
                fresh_command=["tool", "--json"],
                resume_command=["tool", "resume", "$${SESSION_ID}", "${SESSION_ID}"],
            ),
        )
        self.registry.register(custom)

        invocation, error = self.executor.prepare_invocation(
            "custom_session",
            ProviderParams(),
            {},
            "Test prompt",
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
        )

        assert error is None
        assert invocation is not None
        assert invocation.command == ["tool", "resume", "${SESSION_ID}", "sess-123"]

    @patch('subprocess.run')
    def test_provider_execution_success(self, mock_run):
        """Test successful provider execution."""
        # Mock successful execution
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"Success output",
            stderr=b""
        )

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "claude",
            params,
            context,
            "Test prompt"
        )

        assert error is None

        # Execute
        result = self.executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"Success output"
        assert result.error is None

    @patch('subprocess.run')
    def test_provider_timeout(self, mock_run):
        """Test provider timeout handling (exit 124)."""
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude"],
            timeout=30,
            output=b"Partial output",
            stderr=b"Timeout"
        )

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "claude",
            params,
            context,
            "Test prompt",
            timeout_sec=30
        )

        assert error is None

        # Execute with timeout
        result = self.executor.execute(invocation)

        assert result.exit_code == 124  # Timeout exit code
        assert result.stdout == b"Partial output"
        assert result.error["type"] == "timeout"

    def test_session_execution_normalizes_codex_jsonl_stdout(self):
        """Session-enabled Codex transport is parsed into normalized assistant stdout."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"hello "}\n'
            '{"type":"assistant.message","role":"assistant","text":"world"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        raw_stdout_bytes = raw_stdout.encode("utf-8")
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"hello world"
        assert result.raw_stdout == raw_stdout_bytes
        assert result.provider_session == {
            "session_id": "sess-123",
            "normalized_stdout": "hello world",
            "event_count": 4,
        }

    def test_session_execution_turn_failed_exit_zero_is_not_promotable(self):
        """An exact failed-turn event defeats a successful child exit."""
        raw_stdout = (
            '{"type":"thread.started","thread_id":"thread-failed"}\n'
            '{"type":"turn.started"}\n'
            '{"type":"turn.failed"}\n'
        )
        invocation = ProviderInvocation(
            command=[
                "python",
                "-c",
                f"import sys; sys.stdout.write({raw_stdout!r})",
            ],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=(
                ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
            ),
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.FRESH,
            ),
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 2
        assert result.is_promotable is False
        assert result.raw_stdout == raw_stdout.encode("utf-8")
        assert result.stdout == b""
        assert result.provider_session is None
        assert result.error is not None
        assert result.error["type"] == "provider_session_transport_error"

    def test_session_execution_rejects_mismatched_resume_session_id(self):
        """Resume invocations fail when transport reports a different session id."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-other"}\n'
            '{"type":"assistant.message","role":"assistant","text":"hello"}\n'
            '{"type":"response.completed","session_id":"sess-other"}\n'
        )
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="resume_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="sess-123",
            ),
        )

        result = self.executor.execute(invocation)

        assert result.exit_code == 2
        assert result.error is not None
        assert result.error["type"] == "provider_session_transport_error"

    def test_session_stream_output_emits_only_normalized_assistant_text(self, capsys):
        """Session streaming surfaces assistant text, not raw JSONL metadata."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"hello world"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result = self.executor.execute(invocation, stream_output=True)

        assert result.exit_code == 0
        captured = capsys.readouterr()
        assert captured.out == "hello world"
        assert "{\"type\"" not in captured.out

    def test_session_stream_output_emits_normalized_assistant_text_while_process_is_running(self):
        """Session-enabled streaming should surface assistant text before the provider exits."""
        script = (
            "import sys, time; "
            "sys.stdout.write('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.flush(); "
            "time.sleep(0.1); "
            "sys.stdout.write('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}\\n'); "
            "sys.stdout.flush(); "
            "time.sleep(1.0); "
            "sys.stdout.write('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.flush()"
        )
        invocation = ProviderInvocation(
            command=["python", "-c", script],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )
        stdout_recorder = _RecordingBinaryStream()
        stderr_recorder = _RecordingBinaryStream()
        result_box = {}
        started_at = time.time()

        with patch("sys.stdout", stdout_recorder), patch("sys.stderr", stderr_recorder):
            worker = threading.Thread(
                target=lambda: result_box.setdefault(
                    "result",
                    self.executor.execute(invocation, stream_output=True),
                ),
                daemon=True,
            )
            worker.start()

            deadline = time.time() + 0.6
            while time.time() < deadline and stdout_recorder.first_write_at is None:
                time.sleep(0.02)

            first_write_at = stdout_recorder.first_write_at
            worker.join(timeout=5)

        assert first_write_at is not None
        assert first_write_at - started_at < 0.6
        assert result_box["result"].exit_code == 0
        assert stdout_recorder.getvalue() == b"hello"

    def test_session_stream_output_does_not_duplicate_stderr(self):
        """Session-enabled streaming should emit provider stderr exactly once."""
        script = (
            "import sys; "
            "sys.stderr.write('ERR\\n'); sys.stderr.flush(); "
            "sys.stdout.write('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.write('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}\\n'); "
            "sys.stdout.write('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}\\n'); "
            "sys.stdout.flush()"
        )
        invocation = ProviderInvocation(
            command=["python", "-c", script],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )
        stdout_recorder = _RecordingBinaryStream()
        stderr_recorder = _RecordingBinaryStream()

        with patch("sys.stdout", stdout_recorder), patch("sys.stderr", stderr_recorder):
            result = self.executor.execute(invocation, stream_output=True)

        assert result.exit_code == 0
        assert stdout_recorder.getvalue() == b"hello"
        assert stderr_recorder.getvalue() == b"ERR\n"

    def test_session_execution_writes_masked_transport_spool(self):
        """Session transport is masked and copied to the configured spool path."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"secret-token"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        transport_spool_path = self.workspace / "session.transport.log"
        self.executor.secrets_manager._masked_values.add("secret-token")

        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write({raw_stdout!r})"],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result = self.executor.execute(
            invocation,
            session_runtime={"transport_spool_path": transport_spool_path},
        )

        assert result.exit_code == 0
        assert transport_spool_path.exists()
        spool_text = transport_spool_path.read_text(encoding="utf-8")
        assert "***" in spool_text
        assert "secret-token" not in spool_text

    def test_session_execution_appends_transport_spool_while_process_is_running(self):
        """Session transport reaches the stable spool before the provider process exits."""
        raw_stdout = (
            '{"type":"session.started","session_id":"sess-123"}\n'
            '{"type":"assistant.message","role":"assistant","text":"partial"}\n'
            '{"type":"response.completed","session_id":"sess-123"}\n'
        )
        script = (
            "import sys, time; "
            f"payload = {raw_stdout!r}.splitlines(True); "
            "sys.stdout.write(payload[0]); sys.stdout.flush(); "
            "sys.stdout.write(payload[1]); sys.stdout.flush(); "
            "time.sleep(0.8); "
            "sys.stdout.write(payload[2]); sys.stdout.flush()"
        )
        transport_spool_path = self.workspace / "session-live.transport.log"
        invocation = ProviderInvocation(
            command=["python", "-c", script],
            input_mode=InputMode.STDIN,
            prompt="Test prompt",
            command_variant="fresh_command",
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        )

        result_box = {}

        worker = threading.Thread(
            target=lambda: result_box.setdefault(
                "result",
                self.executor.execute(
                    invocation,
                    session_runtime={"transport_spool_path": transport_spool_path},
                ),
            ),
        )
        worker.start()

        deadline = time.time() + 5
        partial_text = ""
        while time.time() < deadline:
            if transport_spool_path.exists():
                partial_text = transport_spool_path.read_text(encoding="utf-8")
                if partial_text:
                    break
            time.sleep(0.02)

        assert partial_text
        assert "session.started" in partial_text
        assert "response.completed" not in partial_text

        worker.join(timeout=5)
        assert not worker.is_alive()
        assert result_box["result"].exit_code == 0

    def test_escape_sequences(self):
        """Test escape sequence handling ($$ and $${)."""
        # Register provider with escapes
        custom = ProviderTemplate(
            name="custom",
            command=["tool", "--text", "$${literal}", "--dollar", "$$100"],
            input_mode=InputMode.ARGV
        )
        self.registry.register(custom)

        params = ProviderParams()
        context = {}

        invocation, error = self.executor.prepare_invocation(
            "custom",
            params,
            context,
            None
        )

        assert error is None
        # Check escapes were processed
        assert "${literal}" in invocation.command  # $${ -> ${
        assert "$100" in invocation.command  # $$ -> $

    def test_streaming_capture_waits_for_reader_threads(self):
        """Streaming capture should return complete stdout even with slow pipe readers."""
        payload = "x" * 9000
        invocation = ProviderInvocation(
            command=["python", "-c", f"import sys; sys.stdout.write('{payload}')"],
            input_mode=InputMode.ARGV,
            prompt=None,
            output_file=None,
            env=None,
            timeout_sec=10,
        )

        def _slow_stream_pipe(pipe, buffer, out_stream):
            if pipe is None:
                return
            output = out_stream.buffer if hasattr(out_stream, "buffer") else out_stream
            try:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    buffer.extend(chunk)
                    time.sleep(1.2)
                    try:
                        output.write(chunk)
                        output.flush()
                    except Exception:
                        pass
            finally:
                pipe.close()

        with patch.object(self.executor, "_stream_pipe", side_effect=_slow_stream_pipe):
            result = self.executor.execute(invocation, stream_output=True)

        assert result.exit_code == 0
        assert len(result.stdout) == len(payload)
        assert result.stdout == payload.encode("utf-8")


# ---------------------------------------------------------------------------
# OMP JSON transport contracts: carrier init, routing, spool, dominance
# ---------------------------------------------------------------------------

_OMP_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "omp" / "protocol"
_OMP_TRANSIENT_FIXTURE = "transient.stdout.jsonl"
_OMP_EXPECTED_BINARY = {
    "platform": "linux",
    "arch": "x86_64",
    "version": "17.3.4",
    "sha256": "f" * 64,
}


def _omp_fixture_bytes() -> bytes:
    return (_OMP_FIXTURE_DIR / _OMP_TRANSIENT_FIXTURE).read_bytes()


def _omp_fixture_header_id() -> str:
    import json

    for line in _omp_fixture_bytes().split(b"\n"):
        if line.startswith(b'{"type":"session"'):
            return json.loads(line)["id"]
    raise AssertionError("fixture has no header")


def _omp_launch_frame(session_id: str) -> bytes:
    import json

    frame = {
        "type": "orchestrator.omp_launch.v1",
        "lane": "ambient",
        "persistence": "none",
        "binary": _OMP_EXPECTED_BINARY,
        "child": {"argv": [], "cwd": "/tmp/work", "env_names": [], "exit_code": 0},
        "session": {
            "id": session_id,
            "visit_key": None,
            "primary_relpath": None,
            "primary_sha256": None,
        },
        "conf": {"manifest_sha256": None},
        "confinement": None,
        "observed": {"advisor_relpaths": [], "child_relpaths": []},
    }
    return json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n"


def _omp_expectation(**overrides):
    from orchestrator.providers.types import OmpTransportExpectation

    base = {
        "lane": "ambient",
        "persistence": "none",
        "binary": _OMP_EXPECTED_BINARY,
        "stdout_session_id": None,
        "visit_key": None,
        "child_argv": (),
        "conf_manifest_sha256": None,
        "confinement_policy_sha256": None,
        "observed_relpaths": (),
    }
    base.update(overrides)
    return OmpTransportExpectation(**base)


def _omp_stream_bytes() -> bytes:
    return _omp_fixture_bytes() + _omp_launch_frame(_omp_fixture_header_id())


def _omp_invocation(*, expectation=None, **overrides) -> ProviderInvocation:
    kwargs = dict(
        command=[
            sys.executable,
            "-c",
            "import os,sys;sys.stdout.buffer.write(%r)" % _omp_stream_bytes(),
        ],
        input_mode=InputMode.STDIN,
        prompt="prompt",
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        omp_transport_expectation=(
            _omp_expectation() if expectation is None else expectation
        ),
    )
    kwargs.update(overrides)
    return ProviderInvocation(**kwargs)


def test_command_metadata_mode_initializes_invocation_and_session_overrides():
    provider = ProviderTemplate(
        name="omp",
        command=[sys.executable, "-m", "orchestrator.providers.omp_launch", "--no-session"],
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(provider)
    executor = ProviderExecutor(Path("."), registry)

    invocation, error = executor.prepare_invocation(
        "omp",
        ProviderParams(),
        {},
        prompt_content="hi",
    )

    assert error is None
    assert invocation is not None
    assert (
        invocation.metadata_mode
        == ProviderSessionMetadataMode.OMP_JSON_STDOUT.value
    )

    session_provider = ProviderTemplate(
        name="omp-session",
        command=[sys.executable, "-m", "orchestrator.providers.omp_launch", "--no-session"],
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        session_support=ProviderSessionSupport(
            metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
            fresh_command=[
                sys.executable,
                "-m",
                "orchestrator.providers.omp_launch",
                "--session",
                "--provider-session-dir",
                "${PROVIDER_SESSION_DIR}",
            ],
        ),
    )
    registry.register(session_provider)

    session_invocation, session_error = executor.prepare_invocation(
        "omp-session",
        ProviderParams(),
        {},
        prompt_content="hi",
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        provider_session_dir="/tmp/omp-visits/step",
    )

    assert session_error is None
    assert session_invocation is not None
    assert (
        session_invocation.metadata_mode
        == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
    )

    template = ProviderTemplate(
        name="omp-default",
        command=["omp"],
        input_mode=InputMode.STDIN,
    )
    assert template.command_metadata_mode is None
    assert template.validate() == []


def test_command_metadata_mode_validation_is_closed():
    from orchestrator.providers.types import ProviderTemplate as Template

    template = Template(
        name="bad",
        command=["omp"],
        input_mode=InputMode.STDIN,
        command_metadata_mode=7,
    )

    errors = template.validate()

    assert any("command_metadata_mode" in error for error in errors)


def test_omp_execution_requires_parent_derived_expectation():
    executor = ProviderExecutor(Path("."), ProviderRegistry())
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.ARGV,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )

    result = executor.execute(invocation)

    assert result.exit_code != 0
    assert result.error is not None
    assert "expectation" in result.error["message"].lower()


@pytest.mark.parametrize(
    "controlled,stream_output,with_observation",
    (
        (False, False, False),
        (False, True, False),
        (False, False, True),
        (True, False, False),
    ),
)
def test_omp_transport_routes_through_all_executor_paths(
    tmp_path,
    controlled,
    stream_output,
    with_observation,
):
    invocation = _omp_invocation()

    kwargs = {}
    if controlled:
        kwargs["control"] = ProviderExecutionControl()
    if with_observation:
        observation = _RecordingObservation()
        kwargs["observation_handle"] = observation.handle

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(
        invocation,
        stream_output=stream_output,
        **kwargs,
    )

    assert result.exit_code == 0
    assert result.error is None
    assert result.raw_stdout == _omp_stream_bytes()
    assert result.stdout == b"OK"
    assert result.provider_session is not None
    assert result.provider_session["session_id"] == _omp_fixture_header_id()
    assert result.provider_session["event_count"] == 11
    if with_observation:
        assert observation.appended == [b"OK"]


class _RecordingObservation:
    def __init__(self) -> None:
        self.appended: list[bytes] = []

        class _Handle:
            def __init__(self, owner: "_RecordingObservation") -> None:
                self._owner = owner

            def check_health(self) -> bool:
                return True

            def append_display(self, data: bytes) -> None:
                self._owner.appended.append(data)

            def finalize(self):
                return {"status": "finalized"}

        self.handle = _Handle(self)


def test_omp_persistence_remains_driven_solely_by_session_request(
    tmp_path,
):
    transient = _omp_invocation()
    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(transient)

    assert result.exit_code == 0
    assert result.provider_session is not None
    assert result.provider_session["event_count"] == 11


def test_omp_execution_never_appends_raw_stdout_to_transport_spool(
    tmp_path,
):
    spool = tmp_path / "session.spool"
    invocation = _omp_invocation()

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(
        invocation,
        session_runtime={"transport_spool_path": spool},
    )

    assert result.exit_code == 0
    assert not spool.exists()


def test_omp_nonzero_child_exit_stays_failure_after_complete_stream(
    tmp_path,
):
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            (
                "import sys;sys.stdout.buffer.write(%r);sys.stdout.flush();"
                "sys.stderr.write('boom');sys.stderr.flush();sys.exit(3)"
            )
            % _omp_stream_bytes(),
        ],
        input_mode=InputMode.ARGV,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        omp_transport_expectation=_omp_expectation(),
    )

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(invocation)

    assert result.exit_code == 3
    assert result.error is None
    assert result.stdout == b"OK"
    assert result.is_promotable is False


def test_omp_live_streaming_display_is_projected_but_capture_is_raw(
    tmp_path,
    capsys,
):
    text = "ok\x1b]0;title\x07\r\x00tail"
    event = {
        "type": "message_end",
        "message": {
            "role": "assistant",
            "api": "api",
            "provider": "provider",
            "model": "model",
            "timestamp": 1,
            "stopReason": "stop",
            "content": [{"type": "text", "text": text}],
            "usage": {
                "input": 1,
                "output": 1,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 2,
                "cost": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "total": 0,
                },
            },
        },
    }
    import json

    header = _omp_fixture_bytes().split(b"\n")[0]
    stream = b"\n".join(
        (
            header,
            b'{"type":"agent_start"}',
            b'{"type":"turn_start"}',
            b'{"type":"message_start","message":{"role":"assistant","content":[]}}',
            json.dumps(event, separators=(",", ":")).encode("utf-8"),
            b'{"type":"agent_end","messages":[]}',
        )
    ) + b"\n" + _omp_launch_frame(_omp_fixture_header_id())
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import os,sys;sys.stdout.buffer.write(%r)" % stream,
        ],
        input_mode=InputMode.ARGV,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        omp_transport_expectation=_omp_expectation(),
    )

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(
        invocation,
        stream_output=True,
    )

    assert result.exit_code == 0
    assert result.raw_stdout == stream
    assert result.stdout == text.encode("utf-8")
    projected = capsys.readouterr().out
    assert "ok" in projected
    assert "\\u001b]0;title\\u0007\\u000d\\u0000tail" in projected
    assert "\x1b" not in projected


def _omp_malformed_stream_bytes(kind: str) -> bytes:
    import json

    lines = [line for line in _omp_fixture_bytes().split(b"\n") if line]
    if kind == "deep_opaque":
        deep = (
            b'{"type":"future.event","payload":'
            + b"[" * 20000
            + b"]" * 20000
            + b"}"
        )
        lines = lines[:1] + [deep] + lines[1:]
    elif kind == "huge_usage":
        message_end = json.loads(lines[9])
        message_end["message"]["usage"]["totalTokens"] = 10**400
        lines = (
            lines[:9]
            + [json.dumps(message_end, separators=(",", ":")).encode()]
            + lines[10:]
        )
    else:
        raise AssertionError(f"unknown malformed kind {kind!r}")
    return (
        b"\n".join(lines)
        + b"\n"
        + _omp_launch_frame(_omp_fixture_header_id())
    )


@pytest.mark.parametrize("malformed_kind", ("deep_opaque", "huge_usage"))
@pytest.mark.parametrize(
    "controlled,stream_output,with_observation",
    (
        (False, False, False),
        (False, True, False),
        (False, False, True),
        (True, False, False),
    ),
)
def test_omp_transport_malformed_line_cannot_settle_across_routes(
    tmp_path,
    controlled,
    stream_output,
    with_observation,
    malformed_kind,
):
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import os,sys;sys.stdout.buffer.write(%r)"
            % _omp_malformed_stream_bytes(malformed_kind),
        ],
        input_mode=InputMode.ARGV,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        omp_transport_expectation=_omp_expectation(),
    )
    kwargs = {}
    if controlled:
        kwargs["control"] = ProviderExecutionControl()
    if with_observation:
        observation = _RecordingObservation()
        kwargs["observation_handle"] = observation.handle

    result = ProviderExecutor(tmp_path, ProviderRegistry()).execute(
        invocation,
        stream_output=stream_output,
        **kwargs,
    )

    assert result.is_promotable is False
    assert result.error is not None
    if controlled:
        # The controlled identity boundary cannot be proven for an invalid
        # transport, so the executor reports the boundary failure instead;
        # either way the malformed stream never normalizes.
        assert result.error["type"] in {
            "provider_session_transport_error",
            "provider_cancellation_boundary_failed",
        }
    else:
        assert result.error["type"] == "provider_session_transport_error"
    assert result.stdout != b"OK"


def test_omp_timeout_kills_the_whole_process_group(tmp_path):
    """Timeout must SIGKILL the entire provider process group (finding 12).

    The OMP adapter spawns the OMP child as its grandchild; killing only the
    wrapper leaves the grandchild holding the stdout pipe, so the executor's
    pipe joins never complete and the invocation hangs past the timeout.
    """
    wrapper = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "time.sleep(60)\n"
    )
    invocation = _omp_invocation(
        command=[sys.executable, "-c", wrapper],
        timeout_sec=2,
    )
    executor = ProviderExecutor(tmp_path, ProviderRegistry())

    results: dict = {}

    def _run() -> None:
        results["result"] = executor.execute(invocation)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=20)

    assert not thread.is_alive(), "timeout must kill the group and return"
    result = results.get("result")
    assert result is not None
    assert result.exit_code == 124


# ---------------------------------------------------------------------------
# Task 5 fix round 2: RED-first regression suite (re-review findings 5, 6)
# ---------------------------------------------------------------------------


def _omp_profile_env(tmp_path) -> dict:
    home = tmp_path / "home"
    (home / ".omp" / "agent" / "agents").mkdir(parents=True, exist_ok=True)
    (home / ".omp" / "agent" / "agents" / "custom.md").write_text(
        "---\nname: custom\ndescription: test agent\n---\nbody\n",
        encoding="utf-8",
    )
    home.chmod(0o700)
    env = {
        "HOME": str(home),
        "TMPDIR": str(tmp_path / "tmp"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "PATH": "/usr/bin:/bin",
    }
    for value in env.values():
        if value.startswith(str(tmp_path)):
            from pathlib import Path as _P
            _P(value).mkdir(parents=True, exist_ok=True)
    return env


def _omp_profile_registry():
    from orchestrator.providers.omp_templates import omp_templates

    registry = ProviderRegistry()
    for name, template in omp_templates().items():
        registry.register(template)
    return registry


def test_omp_conf_prepare_rejects_malformed_conf_tree(tmp_path) -> None:
    """NEW-T5-FIX-001: malformed conf returns validation_error, never escapes."""
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "config.yml").write_text(
        "advisor:\n  enabled: maybe\n", encoding="utf-8"
    )
    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    invocation, error = executor.prepare_invocation(
        "omp_conf",
        ProviderParams(params={"omp_conf_root": str(conf)}),
        {},
        prompt_content="hi",
        env=_omp_profile_env(tmp_path),
    )
    assert invocation is None
    assert error is not None
    assert error["type"] == "validation_error", error

def test_omp_conf_prepare_uses_retained_fd_after_conf_path_swap(
    tmp_path
) -> None:
    import json
    from orchestrator.providers.omp_launch_policy import (
        ATTEMPT_FDS_ENV,
        EMPTY_CWD_ENV,
    )

    conf = tmp_path / "conf"
    conf.mkdir()
    from orchestrator.providers.omp_launch import neutral_conf_root
    (conf / "config.yml").write_bytes(
        (Path(neutral_conf_root()) / "config.yml").read_bytes()
    )
    conf_fd = os.open(
        conf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    original = tmp_path / "conf-original"
    os.replace(conf, original)
    conf.mkdir()
    (conf / "config.yml").write_text("advisor:\n  enabled: maybe\n")
    executor = ProviderExecutor(
        tmp_path, _omp_profile_registry(), profile_conf_fd=conf_fd
    )
    try:
        invocation, error = executor.prepare_invocation(
            "omp_conf",
            ProviderParams(params={"omp_conf_root": str(conf)}),
            {},
            prompt_content="hi",
            env=_omp_profile_env(tmp_path),
        )
        assert error is None, error
        assert invocation is not None
        carrier = json.loads(invocation.env[ATTEMPT_FDS_ENV])
        inherited = os.fstat(carrier["roots"]["__conf__"])
        admitted = os.fstat(conf_fd)
        assert (inherited.st_dev, inherited.st_ino) == (
            admitted.st_dev, admitted.st_ino
        )
    finally:
        os.close(conf_fd)
    invocation.inherited_fd_authority.close()
    os.rmdir(invocation.env[EMPTY_CWD_ENV])


def test_omp_profile_prepare_cleans_empty_cwd_on_failure(tmp_path, monkeypatch) -> None:
    """NEW-T5-FIX-002: a post-create failure must not leave the empty cwd or
    the attempt tree behind (R2: the attempt tree is adapter-owned and must
    never linger after a failed prepare)."""
    from orchestrator.providers.omp_write_confinement import (
        ConfinementError,
        canonical_policy_digest as real_canonical_policy_digest,
    )


    env = _omp_profile_env(tmp_path)

    def _boom(*args, **kwargs):
        raise ConfinementError("forced digest failure")

    monkeypatch.setattr(
        "orchestrator.providers.omp_write_confinement.canonical_policy_digest", _boom
    )
    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(),
        {},
        prompt_content="hi",
        env=env,
    )
    assert invocation is None
    assert error is not None
    assert error["type"] == "validation_error", error
    leftovers = list((tmp_path / "home").glob("omp-empty-*"))
    assert leftovers == [], f"post-create failure must clean the empty cwd: {leftovers}"
    attempts = list((tmp_path / "cache" / "omp-i1" / "attempts").glob("omp-attempt-*"))
    assert attempts == [], f"post-create failure must clean the attempt tree: {attempts}"


def test_omp_fresh_prepare_rejects_swapped_logical_visit_identity(
    tmp_path
) -> None:
    from orchestrator.providers.omp_launch_fs import session_dir_identity

    session_dir = tmp_path / "visits" / "root.task__v1"
    session_dir.mkdir(parents=True)
    session_dir.chmod(0o700)
    identity = session_dir_identity(str(session_dir))
    original = session_dir.with_name("root.task__v1-original")
    os.replace(session_dir, original)
    session_dir.mkdir(mode=0o700)
    executor = ProviderExecutor(tmp_path, _omp_profile_registry())

    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(),
        {},
        prompt_content="hi",
        env=_omp_profile_env(tmp_path),
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        provider_session_dir=str(session_dir),
        provider_session_identity=identity,
    )

    assert invocation is None
    assert error is not None
    assert "identity changed" in error["message"]
    assert list(session_dir.iterdir()) == []


def test_omp_profile_prepare_cleans_empty_cwd_on_identity_failure(tmp_path) -> None:
    """NEW-T5-FIX-002: fresh session identity capture failure also cleans."""
    env = _omp_profile_env(tmp_path)
    session_dir = tmp_path / "visits" / "step-1__v1"
    session_dir.mkdir(parents=True)
    session_dir.chmod(0o755)  # group/other accessible -> identity capture fails
    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(),
        {},
        prompt_content="hi",
        env=env,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        provider_session_dir=str(session_dir),
    )
    assert invocation is None
    assert error is not None
    leftovers = list((tmp_path / "home").glob("omp-empty-*"))
    assert leftovers == [], f"identity failure must clean the empty cwd: {leftovers}"


def test_omp_profile_prepare_exact_grammar_and_env_carrier(tmp_path) -> None:
    """Finding 5 + T5-SEC-005: exact adapter argv; cwd/identity ride the
    code-owned internal carriers; authored carriers are rejected."""
    from orchestrator.providers.omp_launch_policy import EMPTY_CWD_ENV
    from orchestrator.providers.omp_templates import DEFAULT_OMP_MODEL
    from orchestrator.providers.omp_launch import neutral_conf_root

    env = _omp_profile_env(tmp_path)
    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(),
        {},
        prompt_content="hi",
        env=env,
    )
    assert error is None, error
    assert invocation is not None
    assert "--empty-cwd" not in invocation.command
    assert invocation.command == [
        sys.executable, "-m", "orchestrator.providers.omp_launch",
        "run", "--lane", "omp_no_tools", "--model", DEFAULT_OMP_MODEL,
        "--conf-root", neutral_conf_root(),
    ]
    assert invocation.env.get(EMPTY_CWD_ENV), "per-invocation cwd rides the carrier"
    assert invocation.omp_transport_expectation is not None
    assert invocation.omp_transport_expectation.child_argv == tuple(
        invocation.command[3:]
    ), "the frozen frame argv is the exact adapter grammar"

    # Authored carriers at the provider/workflow boundary are rejected.
    env2 = {**env, EMPTY_CWD_ENV: "/tmp/evil-cwd"}
    invocation2, error2 = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(),
        {},
        prompt_content="hi",
        env=env2,
    )
    assert invocation2 is None
    assert error2 is not None
    assert "carrier" in error2["message"].lower(), error2


def test_omp_profile_prepare_uses_per_invocation_empty_cwd(tmp_path) -> None:
    """NEW-T5-FIX-002: a stale crashed-run leftover never poisons a fresh prepare."""
    from orchestrator.providers.omp_launch import LANE_POLICY, PROFILE_POLICIES
    from orchestrator.providers.omp_launch_fs import empty_omp_cwd_path
    from orchestrator.providers.omp_write_confinement import profile_root_sets

    env = _omp_profile_env(tmp_path)
    home = str(tmp_path / "home")
    roots = {
        "data": env["XDG_DATA_HOME"],
        "state": env["XDG_STATE_HOME"],
        "cache": env["XDG_CACHE_HOME"],
        "temp": env["TMPDIR"],
    }
    stale = empty_omp_cwd_path(
        home=home, lane="no-tools", workspace=str(tmp_path),
        session_dir=None, conf_root=None, env_roots=roots,
    )
    Path(stale).mkdir(parents=True)
    (Path(stale) / "planted").write_text("x", encoding="utf-8")

    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(),
        {},
        prompt_content="hi",
        env=env,
    )
    assert error is None, error
    assert invocation is not None


def test_omp_prepare_carries_isolated_worktree_root_per_invocation(tmp_path) -> None:
    """R5: the X5 isolated-worktree root is carried per-invocation on the
    immutable expectation (never mutable executor state), so two prepares
    with different child HOMEs each retain their own root."""
    from pathlib import Path

    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    roots = []
    for name in ("home-a", "home-b"):
        env = _omp_profile_env(tmp_path / name)
        invocation, error = executor.prepare_invocation(
            "omp_no_tools",
            ProviderParams(),
            {},
            prompt_content="hi",
            env=env,
        )
        assert error is None, error
        assert invocation is not None
        expectation = invocation.omp_transport_expectation
        assert expectation is not None
        root = expectation.isolated_worktree_root
        assert root is not None and root.endswith(os.path.join(".omp", "wt")), root
        assert str(tmp_path) in root, root
        roots.append(root)
    assert roots[0] != roots[1]


def test_profile_attempt_fds_survive_spawn_and_do_not_leak(tmp_path) -> None:
    import json

    from orchestrator.providers.omp_launch_policy import (
        ATTEMPT_FDS_ENV,
        create_profile_attempt_authority,
        profile_attempt_roots,
    )

    executor = ProviderExecutor(tmp_path, ProviderRegistry())
    cache = tmp_path / "cache"
    cache.mkdir()
    before = len(os.listdir("/proc/self/fd"))
    for index in range(3):
        attempt = profile_attempt_roots(
            env_roots={"cache": str(cache)},
            lane="no-tools",
            workspace=str(tmp_path),
            session_dir=None,
            conf_root=str(tmp_path),
            nonce=f"{index:016x}",
        )
        authority = create_profile_attempt_authority(attempt)
        conf_fd = os.open(
            tmp_path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        authority.root_fds["__conf__"] = conf_fd
        authority.path_fds[str(tmp_path)] = conf_fd
        script = (
            "import json,os,sys;"
            "from orchestrator.providers.omp_launch_policy import "
            "ATTEMPT_FDS_ENV,adopt_profile_attempt_authority,"
            "inherited_profile_conf_fd;"
            "carrier=os.environ[ATTEMPT_FDS_ENV];"
            "a=adopt_profile_attempt_authority(json.loads(sys.argv[1]),carrier);"
            "os.fstat(inherited_profile_conf_fd(carrier));"
            "os.fstat(a.base_fd);a.close();print('ok')"
        )
        invocation = ProviderInvocation(
            command=[sys.executable, "-c", script, json.dumps(attempt)],
            input_mode=InputMode.ARGV,
            env={ATTEMPT_FDS_ENV: authority.carrier()},
            inherited_fds=authority.descriptors,
            inherited_fd_authority=authority,
        )
        result = executor.execute(invocation)
        assert result.exit_code == 0, result.stderr
        assert result.stdout == b"ok\n"
        assert not os.path.exists(os.path.dirname(attempt["HOME"]))
    assert len(os.listdir("/proc/self/fd")) == before


def test_omp_fresh_revalidation_rejects_drifted_non_primary_entry(tmp_path) -> None:
    """R5 (T5-SEC-006): the parent final acceptance re-runs the shared
    close-time observer on ONE retained visit fd; a racer that adds a valid
    child journal after the adapter framed the empty observed lists must fail
    the launch even though the primary journal still matches."""
    import hashlib
    from pathlib import Path

    from orchestrator.providers.omp_launch import binary_projection
    from orchestrator.providers.omp_launch_fs import session_dir_identity
    from orchestrator.providers.omp_pin import OMP_BINARY_PIN
    from orchestrator.providers.types import OmpTransportExpectation

    fixtures = Path(__file__).parent / "fixtures" / "omp" / "sessions"
    primary_fixture = "2026-08-23T22-33-31-340Z_11111111-1111-7111-8111-111111111111.jsonl"
    session_id = "11111111-1111-7111-8111-111111111111"
    env = _omp_profile_env(tmp_path)
    session_dir = tmp_path / "visits" / "step-1__v1"
    session_dir.mkdir(parents=True)
    session_dir.chmod(0o700)
    journal = session_dir / primary_fixture
    journal.write_bytes((fixtures / primary_fixture).read_bytes())
    identity = session_dir_identity(str(session_dir))
    expectation = OmpTransportExpectation(
        lane="no-tools",
        persistence="fresh",
        binary=binary_projection(OMP_BINARY_PIN),
        visit_key="v1",
        session_dir_identity=identity,
        confinement_policy_sha256="0" * 64,
    )
    invocation = ProviderInvocation(
        command=[
            sys.executable, "-m", "orchestrator.providers.omp_launch",
            "run", "--lane", "omp_no_tools", "--model", "m",
        ],
        input_mode=InputMode.STDIN,
        env=env,
        metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        provider_session_dir=str(session_dir),
        omp_transport_expectation=expectation,
    )
    framed_sha = hashlib.sha256(journal.read_bytes()).hexdigest()
    provider_session = {
        "launch_frame": {
            "session": {
                "id": session_id,
                "primary_relpath": journal.name,
                "primary_sha256": framed_sha,
            },
            "observed": {"advisor_relpaths": [], "child_relpaths": []},
        }
    }
    # Racer adds a VALID settled child journal after the adapter framed the
    # empty observed lists: the primary still matches, but the shared
    # observer's recursive classification now disagrees with the frame.
    artifacts = session_dir / primary_fixture[: -len(".jsonl")]
    artifacts.mkdir()
    (artifacts / "alpha.jsonl").write_bytes(
        (fixtures / "alpha.jsonl").read_bytes()
    )
    executor = ProviderExecutor(tmp_path, _omp_profile_registry())
    error = executor._revalidate_fresh_session(invocation, provider_session)
    assert error is not None, "non-primary drift must fail the final acceptance"
    assert error["type"] == "session_revalidation_failed", error


def test_no_tools_private_conf_carrier_controls_argv_and_expected_manifest(
    tmp_path, monkeypatch
) -> None:
    import shutil
    from orchestrator.providers.omp_conf import admit_conf_tree
    from orchestrator.providers.omp_launch import neutral_conf_root

    private_conf = tmp_path / "source-private-conf"
    shutil.copytree(neutral_conf_root(), private_conf)
    conf_fd = os.open(private_conf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        conf_stat = os.fstat(conf_fd)
        expected_identity = (conf_stat.st_dev, conf_stat.st_ino)
        expected_digest = admit_conf_tree(conf_fd).manifest_sha256
    finally:
        os.close(conf_fd)
    monkeypatch.setattr(
        "orchestrator.providers.omp_launch.neutral_conf_root",
        lambda: (_ for _ in ()).throw(AssertionError("neutral conf reopened")),
    )
    env = _omp_profile_env(tmp_path)
    session_dir = tmp_path / "visits" / "task__v1"
    session_dir.mkdir(parents=True)
    session_dir.chmod(0o700)
    executor = ProviderExecutor(
        tmp_path,
        _omp_profile_registry(),
        no_tools_conf_root=str(private_conf),
        no_tools_conf_identity=expected_identity,
        no_tools_conf_manifest_sha256=expected_digest,
    )
    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(params={}),
        {},
        "prompt",
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        env=env,
        provider_session_dir=str(session_dir),
    )
    assert error is None
    assert invocation is not None
    conf_index = invocation.command.index("--conf-root") + 1
    assert invocation.command[conf_index] == str(private_conf)
    assert invocation.omp_transport_expectation.conf_manifest_sha256 == expected_digest


def test_no_tools_private_conf_carrier_rejects_swap_before_first_open(tmp_path) -> None:
    import shutil
    from orchestrator.providers.omp_conf import admit_conf_tree
    from orchestrator.providers.omp_launch import neutral_conf_root

    private_conf = tmp_path / "source-private-conf"
    shutil.copytree(neutral_conf_root(), private_conf)
    descriptor = os.open(private_conf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        kind = os.fstat(descriptor)
        identity = (kind.st_dev, kind.st_ino)
        digest = admit_conf_tree(descriptor).manifest_sha256
    finally:
        os.close(descriptor)
    private_conf.rename(tmp_path / "old")
    shutil.copytree(neutral_conf_root(), private_conf)

    executor = ProviderExecutor(
        tmp_path,
        _omp_profile_registry(),
        no_tools_conf_root=str(private_conf),
        no_tools_conf_identity=identity,
        no_tools_conf_manifest_sha256=digest,
    )
    invocation, error = executor.prepare_invocation(
        "omp_no_tools",
        ProviderParams(params={}),
        {},
        "prompt",
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        env=_omp_profile_env(tmp_path),
        provider_session_dir=str(tmp_path / "visits" / "task__v1"),
    )
    assert invocation is None
    assert error and error["type"] == "validation_error"
