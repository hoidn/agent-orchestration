"""Tests for provider template resolution and execution.

Tests acceptance criteria AT-8, AT-9, AT-48, AT-49, AT-50, AT-51.
"""

import json
import os
import pytest
import tempfile
from pathlib import Path

from orchestrator.workflow.types import (
    Step, WorkflowSpec, ProviderTemplate, InputMode, OutputCapture
)
from orchestrator.workflow.loader import WorkflowLoader
from orchestrator.providers import TemplateResolver
from orchestrator.providers.template_resolver import ProviderError
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.state.run_state import StateManager


class TestProviderTemplates:
    """Test provider template resolution."""

    def test_acceptance_at8_argv_mode_with_prompt(self, tmp_path):
        """AT-8: Provider templates compose argv correctly with ${PROMPT}."""
        # Create provider template
        providers = {
            'claude': ProviderTemplate(
                name='claude',
                command=['claude', '-p', '${PROMPT}', '--model', '${model}'],
                defaults={'model': 'claude-sonnet'},
                input_mode=InputMode.ARGV
            )
        }

        # Create input file
        input_file = tmp_path / "prompt.txt"
        input_file.write_text("Analyze this code")

        # Create step
        step = Step(
            name="Analyze",
            provider="claude",
            provider_params={'model': 'claude-opus'},
            input_file="prompt.txt"
        )

        # Resolve template
        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={'run': {'timestamp_utc': '2025-01-15T12:00:00Z'}},
            loop_vars=None
        )

        # Verify argv composition
        assert command == ['claude', '-p', 'Analyze this code', '--model', 'claude-opus']
        assert stdin_input is None
        assert error_ctx == {}

    def test_acceptance_at9_stdin_mode_without_prompt(self, tmp_path):
        """AT-9: Provider with input_mode: stdin receives prompt via stdin."""
        # Create provider template
        providers = {
            'codex': ProviderTemplate(
                name='codex',
                command=['codex', 'exec'],
                defaults={},
                input_mode=InputMode.STDIN
            )
        }

        # Create input file
        input_file = tmp_path / "prompt.txt"
        input_file.write_text("Execute this task")

        # Create step
        step = Step(
            name="Execute",
            provider="codex",
            input_file="prompt.txt"
        )

        # Resolve template
        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={},
            loop_vars=None
        )

        # Verify stdin mode
        assert command == ['codex', 'exec']
        assert stdin_input == b"Execute this task"
        assert error_ctx == {}

    def test_acceptance_at48_missing_placeholders(self, tmp_path):
        """AT-48: Missing placeholder values cause exit 2 with missing_placeholders."""
        # Create provider with unresolved placeholder
        providers = {
            'test': ProviderTemplate(
                name='test',
                command=['tool', '--model', '${model}', '--api-key', '${api_key}'],
                defaults={'model': 'default'},
                input_mode=InputMode.ARGV
            )
        }

        # Step without api_key parameter
        step = Step(
            name="Test",
            provider="test",
            provider_params={}  # api_key not provided
        )

        # Resolve template
        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={},
            loop_vars=None
        )

        # Should have missing placeholder
        assert error_ctx.get('missing_placeholders') == ['api_key']

    def test_acceptance_at49_stdin_mode_with_prompt_rejected(self, tmp_path):
        """AT-49: Provider with input_mode:stdin and ${PROMPT} causes validation error."""
        # Create invalid provider template (stdin mode with ${PROMPT})
        providers = {
            'invalid': ProviderTemplate(
                name='invalid',
                command=['tool', '${PROMPT}'],  # Invalid: ${PROMPT} in stdin mode
                defaults={},
                input_mode=InputMode.STDIN
            )
        }

        # Create step
        step = Step(
            name="Invalid",
            provider="invalid",
            input_file="prompt.txt"
        )

        # Create dummy input file
        (tmp_path / "prompt.txt").write_text("test")

        # Resolve template should raise error
        resolver = TemplateResolver(providers, tmp_path)
        with pytest.raises(ProviderError) as exc_info:
            resolver.build_provider_command(step, context={}, loop_vars=None)

        assert "invalid_prompt_placeholder" in str(exc_info.value)

    def test_acceptance_at50_argv_without_prompt(self, tmp_path):
        """AT-50: Provider argv without ${PROMPT} runs without passing prompt."""
        # Create provider without ${PROMPT} placeholder
        providers = {
            'simple': ProviderTemplate(
                name='simple',
                command=['echo', 'fixed', 'output'],
                defaults={},
                input_mode=InputMode.ARGV
            )
        }

        # Step with input file (but template doesn't use it)
        step = Step(
            name="Simple",
            provider="simple",
            input_file="prompt.txt"
        )

        # Create input file
        (tmp_path / "prompt.txt").write_text("This prompt is ignored")

        # Resolve template
        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={},
            loop_vars=None
        )

        # Command should not include prompt since no ${PROMPT}
        assert command == ['echo', 'fixed', 'output']
        assert stdin_input is None

    def test_acceptance_at51_provider_params_substitution(self, tmp_path):
        """AT-51: Provider params support variable substitution."""
        # Create provider template
        providers = {
            'dynamic': ProviderTemplate(
                name='dynamic',
                command=['tool', '--run', '${run_id}', '--context', '${ctx_value}'],
                defaults={},
                input_mode=InputMode.ARGV
            )
        }

        # Step with dynamic params using variables
        step = Step(
            name="Dynamic",
            provider="dynamic",
            provider_params={
                'run_id': '${run.id}',
                'ctx_value': '${context.environment}'
            }
        )

        # Resolve with context
        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={
                'run': {'id': 'run-123'},
                'context': {'environment': 'production'}
            },
            loop_vars=None
        )

        # Verify substitution worked
        assert command == ['tool', '--run', 'run-123', '--context', 'production']
        assert error_ctx == {}

    def test_provider_defaults_override(self, tmp_path):
        """Test that provider_params override defaults."""
        providers = {
            'test': ProviderTemplate(
                name='test',
                command=['tool', '--model', '${model}', '--temp', '${temperature}'],
                defaults={'model': 'default-model', 'temperature': '0.7'},
                input_mode=InputMode.ARGV
            )
        }

        step = Step(
            name="Test",
            provider="test",
            provider_params={'model': 'custom-model'}  # Override model but not temperature
        )

        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={},
            loop_vars=None
        )

        # Model should be overridden, temperature should use default
        assert command == ['tool', '--model', 'custom-model', '--temp', '0.7']

    def test_loop_variables_in_provider(self, tmp_path):
        """Test loop variables substitution in provider commands."""
        providers = {
            'loop': ProviderTemplate(
                name='loop',
                command=['process', '--item', '${item}', '--index', '${index}'],
                defaults={},
                input_mode=InputMode.ARGV
            )
        }

        step = Step(
            name="Process",
            provider="loop",
            provider_params={
                'item': '${item}',
                'index': '${loop.index}'
            }
        )

        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={},
            loop_vars={'item': 'file.txt', 'loop.index': '3', 'loop.total': '10'}
        )

        assert command == ['process', '--item', 'file.txt', '--index', '3']

    def test_escape_sequences_in_provider(self, tmp_path):
        """Test escape sequences in provider commands."""
        providers = {
            'escape': ProviderTemplate(
                name='escape',
                command=['echo', '$${literal}', '$$DOLLAR'],
                defaults={'literal': 'value'},
                input_mode=InputMode.ARGV
            )
        }

        step = Step(
            name="Escape",
            provider="escape"
        )

        resolver = TemplateResolver(providers, tmp_path)
        command, stdin_input, error_ctx = resolver.build_provider_command(
            step,
            context={},
            loop_vars=None
        )

        # Escapes should be processed
        assert command == ['echo', '${literal}', '$DOLLAR']


class TestProviderExecution:
    """Test provider execution with StepExecutor."""

    def test_provider_execution_with_executor(self, tmp_path):
        """Test full provider execution through StepExecutor."""
        # Set up test environment
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        run_root = tmp_path / "runs" / "test-run"
        run_root.mkdir(parents=True)

        # Create input file
        (workspace / "prompt.txt").write_text("Test prompt")

        # Create provider templates
        providers = {
            'echo': ProviderTemplate(
                name='echo',
                command=['echo', '${PROMPT}'],
                defaults={},
                input_mode=InputMode.ARGV
            )
        }

        # Create step
        step = Step(
            name="Echo",
            provider="echo",
            input_file="prompt.txt",
            output_capture=OutputCapture.TEXT
        )

        # Execute step
        executor = StepExecutor(workspace, run_root, providers)
        state, result = executor.execute(step, context={}, loop_vars=None)

        # Verify execution
        assert state.exit_code == 0
        assert result.stdout == b"Test prompt\n"
        assert state.status == "completed"

    def test_provider_missing_placeholders_execution(self, tmp_path):
        """Test execution with missing placeholders causes exit 2."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        run_root = tmp_path / "runs" / "test-run"
        run_root.mkdir(parents=True)

        # Provider with required parameter
        providers = {
            'api': ProviderTemplate(
                name='api',
                command=['curl', '${api_url}'],
                defaults={},
                input_mode=InputMode.ARGV
            )
        }

        # Step without required parameter
        step = Step(
            name="API",
            provider="api"
        )

        # Execute step
        executor = StepExecutor(workspace, run_root, providers)
        state, result = executor.execute(step, context={}, loop_vars=None)

        # Should fail with exit code 2
        assert state.exit_code == 2
        assert state.status == "failed"
        assert "missing_placeholders" in state.error.get("context", {})
        assert state.error["context"]["missing_placeholders"] == ["api_url"]

    def test_provider_stdin_mode_execution(self, tmp_path):
        """Test stdin mode provider execution."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        run_root = tmp_path / "runs" / "test-run"
        run_root.mkdir(parents=True)

        # Create input file
        (workspace / "input.txt").write_text("stdin content")

        # Stdin mode provider (cat reads from stdin)
        providers = {
            'stdin_test': ProviderTemplate(
                name='stdin_test',
                command=['cat'],  # Will read from stdin
                defaults={},
                input_mode=InputMode.STDIN
            )
        }

        step = Step(
            name="StdinTest",
            provider="stdin_test",
            input_file="input.txt",
            output_capture=OutputCapture.TEXT
        )

        # Execute step
        executor = StepExecutor(workspace, run_root, providers)
        state, result = executor.execute(step, context={}, loop_vars=None)

        # Verify stdin was passed
        assert state.exit_code == 0
        assert result.stdout == b"stdin content"