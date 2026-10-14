"""
Tests for secrets handling system.
Validates AT-41,42,54,55: Secrets handling, masking, and precedence.
"""

import os
from unittest.mock import Mock, patch

from orchestrator.security.secrets import (
    SecretsManager,
    SecretsMaskingFilter,
)
from orchestrator.exec.step_executor import StepExecutor


class TestSecretsManager:
    """Test the SecretsManager class."""

    def test_at54_secrets_sourced_from_environment(self):
        """AT-54: Secrets are sourced exclusively from orchestrator environment."""
        manager = SecretsManager()

        # Set up test environment
        with patch.dict(os.environ, {'TEST_SECRET': 'secret_value', 'DB_PASSWORD': 'dbpass123'}):
            context = manager.resolve_secrets(
                declared_secrets=['TEST_SECRET', 'DB_PASSWORD']
            )

            assert context.missing_secrets == []
            assert context.secret_values['TEST_SECRET'] == 'secret_value'
            assert context.secret_values['DB_PASSWORD'] == 'dbpass123'
            assert context.child_env['TEST_SECRET'] == 'secret_value'
            assert context.child_env['DB_PASSWORD'] == 'dbpass123'

    def test_at41_missing_secrets_detected(self):
        """AT-41: Missing declared secrets yield exit 2 with missing_secrets context."""
        manager = SecretsManager()

        # Clear any existing env vars
        with patch.dict(os.environ, {}, clear=True):
            context = manager.resolve_secrets(
                declared_secrets=['MISSING_SECRET', 'ANOTHER_MISSING']
            )

            assert context.missing_secrets == ['MISSING_SECRET', 'ANOTHER_MISSING']
            assert 'MISSING_SECRET' not in context.child_env
            assert 'ANOTHER_MISSING' not in context.child_env

    def test_empty_string_counts_as_present(self):
        """Empty string values count as present per spec."""
        manager = SecretsManager()

        with patch.dict(os.environ, {'EMPTY_SECRET': ''}):
            context = manager.resolve_secrets(
                declared_secrets=['EMPTY_SECRET']
            )

            assert context.missing_secrets == []
            assert context.secret_values['EMPTY_SECRET'] == ''
            assert context.child_env['EMPTY_SECRET'] == ''

    def test_at55_env_precedence(self):
        """AT-55: Step env wins on conflicts with secrets; still masked."""
        manager = SecretsManager()

        with patch.dict(os.environ, {'API_KEY': 'original_secret'}):
            context = manager.resolve_secrets(
                declared_secrets=['API_KEY'],
                step_env={'API_KEY': 'override_value'}
            )

            # No missing secrets
            assert context.missing_secrets == []
            # Step env overrides
            assert context.child_env['API_KEY'] == 'override_value'
            # But value is still tracked for masking
            assert context.secret_values['API_KEY'] == 'override_value'

    def test_at42_secret_masking_in_text(self):
        """AT-42: Secret values are masked as '***' in text."""
        manager = SecretsManager()

        with patch.dict(os.environ, {'PASSWORD': 'supersecret123', 'API_KEY': 'key_abcd1234'}):
            context = manager.resolve_secrets(
                declared_secrets=['PASSWORD', 'API_KEY']
            )

            # Test text masking
            text = "Connection string: user@host/db?password=supersecret123&api_key=key_abcd1234"
            masked = manager.mask_text(text)

            assert 'supersecret123' not in masked
            assert 'key_abcd1234' not in masked
            assert '***' in masked
            # Should mask both values
            assert masked == "Connection string: user@host/db?password=***&api_key=***"

    def test_masking_preserves_non_secret_text(self):
        """Masking only affects secret values, preserving other text."""
        manager = SecretsManager()

        with patch.dict(os.environ, {'SECRET': 'hidden'}):
            context = manager.resolve_secrets(declared_secrets=['SECRET'])

            text = "This is public text with hidden value and more public text"
            masked = manager.mask_text(text)

            assert masked == "This is public text with *** value and more public text"
            assert 'public text' in masked
            assert 'hidden' not in masked

    def test_mask_dict_recursive(self):
        """Test recursive dictionary masking."""
        manager = SecretsManager()

        with patch.dict(os.environ, {'TOKEN': 'abc123'}):
            context = manager.resolve_secrets(declared_secrets=['TOKEN'])

            data = {
                'command': 'curl -H "Authorization: Bearer abc123"',
                'nested': {
                    'value': 'abc123',
                    'list': ['item', 'abc123', 'other']
                }
            }

            masked = manager.mask_dict(data)

            assert masked['command'] == 'curl -H "Authorization: Bearer ***"'
            assert masked['nested']['value'] == '***'
            assert masked['nested']['list'] == ['item', '***', 'other']

    def test_environment_composition(self):
        """Test full environment composition: inherit, overlay secrets, apply step env."""
        manager = SecretsManager()

        # Setup complex environment scenario
        base_env = {'BASE_VAR': 'base', 'SHARED': 'original'}
        with patch.dict(os.environ, base_env, clear=True):
            with patch.dict(os.environ, {'SECRET1': 'sec1', 'SECRET2': 'sec2'}):
                context = manager.resolve_secrets(
                    declared_secrets=['SECRET1', 'SECRET2'],
                    step_env={'SHARED': 'step_override', 'STEP_VAR': 'step_value'}
                )

                # Check final environment
                assert context.child_env['BASE_VAR'] == 'base'  # Inherited
                assert context.child_env['SECRET1'] == 'sec1'  # Secret
                assert context.child_env['SECRET2'] == 'sec2'  # Secret
                assert context.child_env['SHARED'] == 'step_override'  # Step override
                assert context.child_env['STEP_VAR'] == 'step_value'  # Step-specific


class TestSecretsMaskingFilter:
    """Test the logging filter for secrets masking."""

    def test_log_record_masking(self):
        """Test masking in log records."""
        manager = SecretsManager()

        with patch.dict(os.environ, {'PASSWORD': 'secret123'}):
            context = manager.resolve_secrets(declared_secrets=['PASSWORD'])

            filter = SecretsMaskingFilter(manager)

            # Create mock log record
            record = Mock()
            record.msg = "Database password is secret123"
            record.args = None

            # Apply filter
            result = filter.filter(record)

            assert result is True  # Filter should always pass records through
            assert record.msg == "Database password is ***"


class TestStepExecutorWithSecrets:
    """Test step executor with secrets integration."""

    def test_at41_step_execution_with_missing_secrets(self, tmp_path):
        """AT-41: Step fails with exit 2 when secrets are missing."""
        executor = StepExecutor(tmp_path)

        # Clear environment to ensure secrets are missing
        with patch.dict(os.environ, {}, clear=True):
            result = executor.execute_command(
                step_name="test_step",
                command="echo test",
                secrets=["MISSING_SECRET"]
            )

            assert result.exit_code == 2
            assert result.error['type'] == 'missing_secrets'
            assert 'MISSING_SECRET' in result.error['context']['missing_secrets']

    def test_secrets_passed_to_subprocess(self, tmp_path):
        """Test that secrets are properly passed to subprocess environment."""
        executor = StepExecutor(tmp_path)

        with patch.dict(os.environ, {'MY_SECRET': 'value123'}):
            result = executor.execute_command(
                step_name="test_step",
                command="echo $MY_SECRET",
                secrets=["MY_SECRET"]
            )

            assert result.exit_code == 0
            # Output should be masked in capture
            assert 'value123' not in result.capture_result.output
            assert '***' in result.capture_result.output or 'MY_SECRET' in result.capture_result.output

    def test_step_env_precedence_with_secrets(self, tmp_path):
        """Test that step env overrides secrets but is still masked."""
        executor = StepExecutor(tmp_path)

        with patch.dict(os.environ, {'API_KEY': 'original'}):
            result = executor.execute_command(
                step_name="test_step",
                command="echo $API_KEY",
                secrets=["API_KEY"],
                env={"API_KEY": "override"}
            )

            assert result.exit_code == 0
            # Override value should be used but masked
            assert 'override' not in result.capture_result.output
            assert 'original' not in result.capture_result.output


# Integration test demonstrating full flow
