"""
Test execution safety with argv mode (no shell=True).
Validates that commands are executed safely without shell injection risks.
"""

import pytest
import tempfile
from pathlib import Path

from orchestrator.exec.step_executor import StepExecutor


class TestExecutionSafety:
    """Test safe command execution using argv arrays."""

    def test_string_command_parsed_correctly(self, tmp_path):
        """Test that string commands are parsed into argv arrays."""
        executor = StepExecutor(tmp_path)

        # Command with arguments and quotes
        result = executor.execute_command(
            step_name="test",
            command='echo "hello world"',
            output_capture="text"
        )

        assert result.exit_code == 0
        assert "hello world" in result.capture_result.output

    def test_list_command_executed_directly(self, tmp_path):
        """Test that list commands are passed directly as argv."""
        executor = StepExecutor(tmp_path)

        # Command as argv array
        result = executor.execute_command(
            step_name="test",
            command=["echo", "hello", "world"],
            output_capture="text"
        )

        assert result.exit_code == 0
        assert "hello world" in result.capture_result.output

    def test_command_with_special_chars_safe(self, tmp_path):
        """Test that special shell characters are handled safely."""
        executor = StepExecutor(tmp_path)

        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Command with shell metacharacters that should be treated literally
        result = executor.execute_command(
            step_name="test",
            command=['echo', '$HOME', '&&', 'ls'],  # These should be literal strings
            output_capture="text"
        )

        assert result.exit_code == 0
        # The special characters should be printed literally, not executed
        assert "$HOME && ls" in result.capture_result.output

    def test_shell_injection_prevented(self, tmp_path):
        """Test that shell injection attempts are prevented."""
        executor = StepExecutor(tmp_path)

        # This would be dangerous with shell=True
        dangerous_input = "test; rm -rf /"

        # As a string command, shlex.split will parse it safely
        result = executor.execute_command(
            step_name="test",
            command=f'echo "{dangerous_input}"',
            output_capture="text"
        )

        assert result.exit_code == 0
        # The dangerous command should be printed, not executed
        assert "test; rm -rf /" in result.capture_result.output

    def test_command_with_pipes_requires_explicit_shell(self, tmp_path):
        """Test that shell features like pipes don't work without explicit shell."""
        executor = StepExecutor(tmp_path)

        # This would work with shell=True but should fail without it
        # The pipe character will be treated as a literal argument to echo
        result = executor.execute_command(
            step_name="test",
            command="echo hello | grep hello",  # Pipe won't work
            output_capture="text"
        )

        # echo will succeed but output the literal string including the pipe
        assert result.exit_code == 0
        assert "hello | grep hello" in result.capture_result.output

    def test_environment_variable_expansion(self, tmp_path):
        """Test environment variable handling in argv mode."""
        executor = StepExecutor(tmp_path)

        # Set a custom environment variable
        env = {"TEST_VAR": "test_value"}

        # Test with list command - variables are NOT expanded in argv mode
        result = executor.execute_command(
            step_name="test",
            command=["echo", "$TEST_VAR"],  # Will print literal $TEST_VAR
            env=env,
            output_capture="text"
        )

        assert result.exit_code == 0
        # In argv mode, $TEST_VAR is a literal string
        assert "$TEST_VAR" in result.capture_result.output

        # For actual env var usage, use the env command or similar
        result = executor.execute_command(
            step_name="test",
            command=["printenv", "TEST_VAR"],
            env=env,
            output_capture="text"
        )

        assert result.exit_code == 0
        assert "test_value" in result.capture_result.output

    def test_complex_command_parsing(self, tmp_path):
        """Test parsing of complex commands with quotes and spaces."""
        executor = StepExecutor(tmp_path)

        # Complex command with nested quotes and spaces
        result = executor.execute_command(
            step_name="test",
            command='echo "arg with spaces" \'single quotes\' bare_arg',
            output_capture="text"
        )

        assert result.exit_code == 0
        output = result.capture_result.output.strip()
        assert "arg with spaces" in output
        assert "single quotes" in output
        assert "bare_arg" in output

    def test_invalid_command_type_rejected(self, tmp_path):
        """Test that invalid command types are rejected."""
        executor = StepExecutor(tmp_path)

        with pytest.raises(ValueError, match="Invalid command type"):
            executor.execute_command(
                step_name="test",
                command=123,  # Invalid type
                output_capture="text"
            )

    def test_command_not_found_handling(self, tmp_path):
        """Test handling of non-existent commands."""
        executor = StepExecutor(tmp_path)

        result = executor.execute_command(
            step_name="test",
            command=["nonexistent_command_xyz"],
            output_capture="text"
        )

        # Should get an execution error
        assert result.exit_code != 0
        # The error is in the result, not the capture_result
        assert result.error is not None
        assert "execution_error" in result.error.get("type", "")


class TestWorkflowCommandExecution:
    """Test command execution through the workflow executor."""

    def test_workflow_with_list_commands(self, tmp_path):
        """Test that workflows properly handle list commands via direct testing."""
        from orchestrator.exec.step_executor import StepExecutor
        from orchestrator.variables.substitution import VariableSubstitutor

        executor = StepExecutor(tmp_path)
        substitutor = VariableSubstitutor()

        # Test list command directly
        result = executor.execute_command(
            step_name="ListCommand",
            command=['echo', 'test', 'message'],
            output_capture="text"
        )
        assert result.exit_code == 0
        assert 'test message' in result.capture_result.output

        # Test string command directly
        result = executor.execute_command(
            step_name="StringCommand",
            command='echo "another test"',
            output_capture="text"
        )
        assert result.exit_code == 0
        assert 'another test' in result.capture_result.output

    def test_workflow_variable_substitution_in_commands(self, tmp_path):
        """Test variable substitution works with both string and list commands."""
        from orchestrator.exec.step_executor import StepExecutor
        from orchestrator.variables.substitution import VariableSubstitutor

        executor = StepExecutor(tmp_path)
        substitutor = VariableSubstitutor()

        context = {'message': 'hello from context'}

        # Test list command with substitution
        command = ['echo', '${context.message}']
        # Substitute each element
        substituted_command = [substitutor.substitute(elem, {'context': context}, {}) for elem in command]

        result = executor.execute_command(
            step_name="ListWithVars",
            command=substituted_command,
            output_capture="text"
        )
        assert result.exit_code == 0
        assert 'hello from context' in result.capture_result.output

        # Test string command with substitution
        command = 'echo "${context.message}"'
        substituted_command = substitutor.substitute(command, {'context': context}, {})

        result = executor.execute_command(
            step_name="StringWithVars",
            command=substituted_command,
            output_capture="text"
        )
        assert result.exit_code == 0
        assert 'hello from context' in result.capture_result.output