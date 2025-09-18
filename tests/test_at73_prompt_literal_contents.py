"""
Test AT-73: Prompt literal contents
- input_file contents are read and passed literally
- The orchestrator must not substitute variables inside file contents
- Dependency injection may modify the composed prompt in-memory without mutating the source file
"""

import json
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import subprocess

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager


class TestPromptLiteralContents:
    """Test that input_file contents are passed literally without variable substitution (AT-73)"""

    def test_at73_argv_mode_literal_prompt(self, tmp_path):
        """Provider with argv mode receives literal prompt content - no variable substitution"""
        # Prepare workspace with prompt containing variable syntax
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        prompt_dir = workspace / "prompts"
        prompt_dir.mkdir()

        # Create prompt file with variable-like syntax that should NOT be substituted
        prompt_file = prompt_dir / "test.md"
        prompt_content = "Process this ${context.project} with ${steps.previous.output} and ${undefined.var}"
        prompt_file.write_text(prompt_content)

        # Create workflow
        workflow = {
            'version': '1.1',
            'context': {
                'project': 'test-project'
            },
            'providers': {
                'test-provider': {
                    'command': ['echo', 'Provider', 'output:', '${PROMPT}'],
                    'input_mode': 'argv',
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'TestStep',
                    'provider': 'test-provider',
                    'input_file': 'prompts/test.md',
                    'output_capture': 'text'
                }
            ]
        }

        # Save workflow to file
        workflow_path = workspace / 'workflow.yaml'
        with open(workflow_path, 'w') as f:
            yaml.dump(workflow, f)

        # Create executor
        state_manager = StateManager(
            workspace=workspace,
            run_id='test-run'
        )
        state_manager.initialize('workflow.yaml', {'project': 'test-project'})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=False
        )

        # Mock subprocess.run to capture the exact command
        captured_command = []
        def mock_run(cmd, **kwargs):
            captured_command.clear()
            captured_command.extend(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = b"mocked output"
            result.stderr = b""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            result = executor.execute()

        # Verify the prompt was passed literally
        assert result['status'] == 'completed'

        # The command should have the literal prompt content in place of ${PROMPT}
        assert len(captured_command) == 4
        assert captured_command[0] == 'echo'
        assert captured_command[1] == 'Provider'
        assert captured_command[2] == 'output:'
        # This is the key assertion - prompt should be literal, with ${...} intact
        assert captured_command[3] == prompt_content
        assert '${context.project}' in captured_command[3]
        assert '${steps.previous.output}' in captured_command[3]
        assert '${undefined.var}' in captured_command[3]

    def test_at73_stdin_mode_literal_prompt(self, tmp_path):
        """Provider with stdin mode receives literal prompt content - no variable substitution"""
        # Prepare workspace with prompt containing variable syntax
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        prompt_dir = workspace / "prompts"
        prompt_dir.mkdir()

        # Create prompt file with variable-like syntax that should NOT be substituted
        prompt_file = prompt_dir / "test.md"
        prompt_content = "Analyze ${context.data} using ${loop.index} and ${item}"
        prompt_file.write_text(prompt_content)

        # Create workflow
        workflow = {
            'version': '1.1',
            'context': {
                'data': 'important-data'
            },
            'providers': {
                'stdin-provider': {
                    'command': ['cat'],  # Just echo stdin
                    'input_mode': 'stdin',
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'StdinStep',
                    'provider': 'stdin-provider',
                    'input_file': 'prompts/test.md',
                    'output_capture': 'text'
                }
            ]
        }

        # Save workflow to file
        workflow_path = workspace / 'workflow.yaml'
        with open(workflow_path, 'w') as f:
            yaml.dump(workflow, f)

        # Create executor
        state_manager = StateManager(
            workspace=workspace,
            run_id='test-run'
        )
        state_manager.initialize('workflow.yaml', {'data': 'important-data'})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=False
        )

        # Mock subprocess.run to capture the stdin
        captured_stdin = []
        def mock_run(cmd, **kwargs):
            if 'input' in kwargs:
                captured_stdin.clear()
                # Input is already bytes from provider executor - decode to check content
                input_bytes = kwargs['input']
                captured_stdin.append(input_bytes.decode('utf-8') if isinstance(input_bytes, bytes) else input_bytes)
            result = MagicMock()
            result.returncode = 0
            # Cat echoes stdin - input is already bytes
            result.stdout = kwargs.get('input', b'') if 'input' in kwargs else b''
            result.stderr = b""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            result = executor.execute()

        # Verify the prompt was passed literally
        assert result['status'] == 'completed'

        # The stdin should have the literal prompt content
        assert len(captured_stdin) == 1
        assert captured_stdin[0] == prompt_content
        assert '${context.data}' in captured_stdin[0]
        assert '${loop.index}' in captured_stdin[0]
        assert '${item}' in captured_stdin[0]

    def test_at73_with_dependency_injection_literal(self, tmp_path):
        """With dependency injection, original prompt remains literal; injection adds to it"""
        # Prepare workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        prompt_dir = workspace / "prompts"
        prompt_dir.mkdir()

        deps_dir = workspace / "deps"
        deps_dir.mkdir()

        # Create prompt file with variable syntax
        prompt_file = prompt_dir / "test.md"
        prompt_content = "Use ${context.model} to process ${steps.data.output}"
        prompt_file.write_text(prompt_content)

        # Create dependency file
        dep_file = deps_dir / "config.txt"
        dep_file.write_text("config data")

        # Create workflow with injection
        workflow = {
            'version': '1.1.1',  # Required for injection
            'context': {
                'model': 'gpt-4'
            },
            'providers': {
                'test-provider': {
                    'command': ['echo', '${PROMPT}'],
                    'input_mode': 'argv',
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'TestWithInjection',
                    'provider': 'test-provider',
                    'input_file': 'prompts/test.md',
                    'depends_on': {
                        'required': ['deps/config.txt'],
                        'inject': True  # Will prepend file list
                    },
                    'output_capture': 'text'
                }
            ]
        }

        # Save workflow to file
        workflow_path = workspace / 'workflow.yaml'
        with open(workflow_path, 'w') as f:
            yaml.dump(workflow, f)

        # Create executor
        state_manager = StateManager(
            workspace=workspace,
            run_id='test-run'
        )
        state_manager.initialize('workflow.yaml', {'model': 'gpt-4'})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=False
        )

        # Mock subprocess.run to capture the command
        captured_prompt = []
        def mock_run(cmd, **kwargs):
            if len(cmd) >= 2 and cmd[0] == 'echo':
                captured_prompt.clear()
                captured_prompt.append(cmd[1])
            result = MagicMock()
            result.returncode = 0
            result.stdout = b"output"
            result.stderr = b""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            result = executor.execute()

        assert result['status'] == 'completed'

        # The prompt should have injection PLUS literal content
        assert len(captured_prompt) == 1
        final_prompt = captured_prompt[0]

        # Should have injection header (text may vary)
        assert "deps/config.txt" in final_prompt  # File path should be present
        assert "following required files" in final_prompt.lower()  # Some indication of files

        # Original prompt should be literal (variables NOT substituted)
        assert '${context.model}' in final_prompt
        assert '${steps.data.output}' in final_prompt

    def test_at73_loop_context_literal_prompt(self, tmp_path):
        """In for_each loops, prompt remains literal despite loop variables"""
        # Prepare workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        prompt_dir = workspace / "prompts"
        prompt_dir.mkdir()

        # Create prompt with loop variable references
        prompt_file = prompt_dir / "loop.md"
        prompt_content = "Process item ${item} at index ${loop.index} of ${loop.total}"
        prompt_file.write_text(prompt_content)

        # Create workflow with for_each
        workflow = {
            'version': '1.1',
            'providers': {
                'test-provider': {
                    'command': ['echo', '${PROMPT}'],
                    'input_mode': 'argv',
                    'defaults': {}
                }
            },
            'steps': [
                {
                    'name': 'ProcessItems',
                    'for_each': {
                        'items': ['apple', 'banana', 'cherry'],
                        'steps': [
                            {
                                'name': 'ProcessOne',
                                'provider': 'test-provider',
                                'input_file': 'prompts/loop.md',
                                'output_capture': 'text'
                            }
                        ]
                    }
                }
            ]
        }

        # Save workflow to file
        workflow_path = workspace / 'workflow.yaml'
        with open(workflow_path, 'w') as f:
            yaml.dump(workflow, f)

        # Create executor
        state_manager = StateManager(
            workspace=workspace,
            run_id='test-run'
        )
        state_manager.initialize('workflow.yaml', {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=False
        )

        # Mock the provider executor's execute method directly
        captured_prompts = []
        original_execute = executor.provider_executor.execute

        from orchestrator.providers.executor import ProviderExecutionResult

        def mock_execute(invocation):
            # In argv mode, the prompt content is substituted into the command
            # The command should be ['echo', '<prompt-content>']
            if len(invocation.command) >= 2:
                prompt_from_command = invocation.command[1]  # Second argument after 'echo'
                captured_prompts.append(prompt_from_command)

            # Return a successful result
            return ProviderExecutionResult(
                exit_code=0,
                stdout=b"output",
                stderr=b"",
                duration_ms=10
            )

        executor.provider_executor.execute = mock_execute

        result = executor.execute()

        assert result['status'] == 'completed'

        # Should have executed 3 times (one per item)
        assert len(captured_prompts) == 3, f"Expected 3 prompts, got {len(captured_prompts)}: {captured_prompts}"

        # ALL prompts should be literal - no substitution
        for prompt in captured_prompts:
            assert prompt == prompt_content
            assert '${item}' in prompt
            assert '${loop.index}' in prompt
            assert '${loop.total}' in prompt

    def test_at73_command_step_no_prompt_substitution(self, tmp_path):
        """Command steps don't have input_file, but verify no regression"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        # Create workflow with command that uses variables
        workflow = {
            'version': '1.1',
            'context': {
                'name': 'test-value'
            },
            'steps': [
                {
                    'name': 'CommandStep',
                    'command': ['echo', '${context.name}'],  # Variables in command ARE substituted
                    'output_capture': 'text'
                }
            ]
        }

        # Save workflow to file
        workflow_path = workspace / 'workflow.yaml'
        with open(workflow_path, 'w') as f:
            yaml.dump(workflow, f)

        # Create executor
        state_manager = StateManager(
            workspace=workspace,
            run_id='test-run'
        )
        state_manager.initialize('workflow.yaml', {'name': 'test-value'})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=workspace,
            state_manager=state_manager,
            debug=False
        )

        # Mock subprocess.run
        captured_command = []
        def mock_run(cmd, **kwargs):
            captured_command.clear()
            captured_command.extend(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = b"output"
            result.stderr = b""
            return result

        with patch('subprocess.run', side_effect=mock_run):
            result = executor.execute()

        assert result['status'] == 'completed'

        # Variables in commands ARE still substituted (this is NOT input_file content)
        assert captured_command == ['echo', 'test-value']