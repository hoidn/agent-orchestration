"""
Tests for provider execution per specs/providers.md and acceptance tests.

Tests provider registry, template validation, argv/stdin modes, placeholder
substitution, and error handling.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from orchestrator.providers import (
    ProviderTemplate,
    ProviderParams,
    ProviderRegistry,
    ProviderExecutor,
    InputMode,
)


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
        assert claude.defaults.get("model") == "claude-sonnet-4-20250514"

        # Check codex template (stdin mode)
        codex = registry.get("codex")
        assert codex.name == "codex"
        assert codex.input_mode == InputMode.STDIN
        assert "${PROMPT}" not in " ".join(codex.command)

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

    def test_merge_params(self):
        """Test parameter merging (step params override defaults)."""
        registry = ProviderRegistry()

        # Get claude with defaults
        defaults = registry.merge_params("claude", None)
        assert defaults["model"] == "claude-sonnet-4-20250514"

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