"""
Test AT-66: env literal semantics - orchestrator does not substitute variables inside env values

The orchestrator should pass environment variable values literally without performing
variable substitution (${context.*}, ${steps.*}, etc.). This ensures that shell scripts
and programs receive literal values as intended.
"""

import json
import tempfile
from pathlib import Path
import pytest
from unittest.mock import Mock, patch, MagicMock
import subprocess

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager


class TestAT66EnvLiteralSemantics:
    """Test that env values are passed literally without variable substitution"""

    def test_at66_env_no_substitution_command(self):
        """AT-66: Command steps should not substitute variables in env values"""
        # Create a workflow with env containing variable patterns
        workflow = {
            "version": "1.1",
            "steps": [
                {
                    "name": "InitStep",
                    "command": "echo 'init-value'",
                    "output_capture": "text"
                },
                {
                    "name": "TestEnv",
                    "command": "echo \"VAR1=$VAR1 VAR2=$VAR2 VAR3=$VAR3\"",
                    "env": {
                        "VAR1": "${steps.InitStep.output}",  # Should be literal
                        "VAR2": "${context.some_key}",        # Should be literal
                        "VAR3": "literal-${run.root}-value"   # Should be literal
                    },
                    "output_capture": "text"
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write workflow to file (needed for checksum)
            workflow_file = Path(tmpdir) / "workflow.yaml"
            import yaml
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow, f)

            state_manager = StateManager(workspace=Path(tmpdir), run_id="test-run")
            state_manager.initialize("workflow.yaml", context={'some_key': 'context-value'})

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=Path(tmpdir),
                state_manager=state_manager
            )

            # Mock subprocess to capture env vars
            captured_env = {}
            def capture_subprocess_run(*args, **kwargs):
                # Capture the env passed to subprocess
                if 'env' in kwargs:
                    captured_env.update(kwargs['env'])

                # Return different outputs based on command
                cmd = args[0] if args else kwargs.get('args', [])
                if isinstance(cmd, list) and 'init-value' in ' '.join(cmd):
                    # First command
                    result = MagicMock()
                    result.returncode = 0
                    result.stdout = b'init-value'
                    result.stderr = b''
                    return result
                else:
                    # Second command - echo the env vars literally
                    result = MagicMock()
                    result.returncode = 0
                    # The env vars should contain literal ${...} patterns
                    var1 = captured_env.get('VAR1', '')
                    var2 = captured_env.get('VAR2', '')
                    var3 = captured_env.get('VAR3', '')
                    result.stdout = f"VAR1={var1} VAR2={var2} VAR3={var3}".encode()
                    result.stderr = b''
                    return result

            with patch('orchestrator.exec.step_executor.subprocess.run', side_effect=capture_subprocess_run):
                with patch('orchestrator.providers.executor.subprocess.run', side_effect=capture_subprocess_run):
                    executor.execute()

            # Check that env vars were passed literally
            assert 'VAR1' in captured_env
            assert captured_env['VAR1'] == '${steps.InitStep.output}'  # Literal
            assert captured_env['VAR2'] == '${context.some_key}'        # Literal
            assert captured_env['VAR3'] == 'literal-${run.root}-value'  # Literal

            # Check the captured output shows literal values
            state = state_manager.load().to_dict()
            output = state['steps']['TestEnv']['output']
            assert 'VAR1=${steps.InitStep.output}' in output
            assert 'VAR2=${context.some_key}' in output
            assert 'VAR3=literal-${run.root}-value' in output

    def test_at66_env_no_substitution_provider(self):
        """AT-66: Provider steps should not substitute variables in env values"""
        workflow = {
            "version": "1.1",
            "providers": {
                "test_provider": {
                    "executable": "/bin/echo",
                    "command": "Args: ${args}",
                    "defaults": {
                        "args": "default"
                    }
                }
            },
            "steps": [
                {
                    "name": "InitStep",
                    "command": "echo 'init-value'",
                    "output_capture": "text"
                },
                {
                    "name": "ProviderWithEnv",
                    "provider": "test_provider",
                    "provider_params": {
                        "args": "test"
                    },
                    "env": {
                        "PROVIDER_VAR1": "${steps.InitStep.output}",
                        "PROVIDER_VAR2": "${context.key}",
                        "PROVIDER_VAR3": "fixed-${loop.index}-text"
                    },
                    "output_capture": "text"
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workflow_file = Path(tmpdir) / "workflow.yaml"
            import yaml
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow, f)

            state_manager = StateManager(workspace=Path(tmpdir), run_id="test-run")
            state_manager.initialize("workflow.yaml", context={'key': 'value'})

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=Path(tmpdir),
                state_manager=state_manager
            )

            captured_provider_env = {}
            def capture_subprocess_run(*args, **kwargs):
                if 'env' in kwargs:
                    # Capture all env vars, not just provider ones
                    captured_provider_env.update(kwargs['env'])

                result = MagicMock()
                result.returncode = 0
                result.stdout = b'output'
                result.stderr = b''
                return result

            with patch('orchestrator.exec.step_executor.subprocess.run', side_effect=capture_subprocess_run):
                with patch('orchestrator.providers.executor.subprocess.run', side_effect=capture_subprocess_run):
                    executor.execute()

            # Verify provider env vars were passed literally
            assert 'PROVIDER_VAR1' in captured_provider_env
            assert captured_provider_env['PROVIDER_VAR1'] == '${steps.InitStep.output}'
            assert captured_provider_env['PROVIDER_VAR2'] == '${context.key}'
            assert captured_provider_env['PROVIDER_VAR3'] == 'fixed-${loop.index}-text'

    def test_at66_env_with_secrets_no_substitution(self):
        """AT-66: Env values should be literal even when mixed with secrets"""
        workflow = {
            "version": "1.1",
            "steps": [
                {
                    "name": "TestSecretEnv",
                    "command": "echo 'test'",
                    "secrets": ["SECRET_KEY"],
                    "env": {
                        "LITERAL_VAR": "${steps.NonExistent.output}",
                        "SECRET_KEY": "override-${context.value}"  # Override secret, still literal
                    }
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workflow_file = Path(tmpdir) / "workflow.yaml"
            import yaml
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow, f)

            state_manager = StateManager(workspace=Path(tmpdir), run_id="test-run")
            state_manager.initialize("workflow.yaml", context={'value': 'context-val'})

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=Path(tmpdir),
                state_manager=state_manager
            )

            captured_env = {}
            def capture_subprocess_run(*args, **kwargs):
                if 'env' in kwargs:
                    captured_env.update(kwargs['env'])
                result = MagicMock()
                result.returncode = 0
                result.stdout = b'test'
                result.stderr = b''
                return result

            # Set orchestrator environment secret
            import os
            os.environ['SECRET_KEY'] = 'secret-value'

            try:
                with patch('subprocess.run', side_effect=capture_subprocess_run):
                    executor.execute()

                # Verify env override is literal (AT-55: env wins, but no substitution)
                assert captured_env['SECRET_KEY'] == 'override-${context.value}'  # Literal override
                assert captured_env['LITERAL_VAR'] == '${steps.NonExistent.output}'  # Literal
            finally:
                del os.environ['SECRET_KEY']

    def test_at66_env_in_for_each_literal(self):
        """AT-66: Env values in for_each loops should remain literal"""
        workflow = {
            "version": "1.1",
            "steps": [
                {
                    "name": "LoopTest",
                    "for_each": {
                        "items": ["a", "b"],
                        "steps": [
                            {
                                "name": "LoopCommand",
                                "command": "echo 'test'",
                                "env": {
                                    "LOOP_VAR": "${loop.index}",      # Should be literal
                                    "ITEM_VAR": "${item}",             # Should be literal
                                    "MIXED": "prefix-${steps.X.y}-${loop.total}"  # Should be literal
                                }
                            }
                        ]
                    }
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workflow_file = Path(tmpdir) / "workflow.yaml"
            import yaml
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow, f)

            state_manager = StateManager(workspace=Path(tmpdir), run_id="test-run")
            state_manager.initialize("workflow.yaml")

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=Path(tmpdir),
                state_manager=state_manager
            )

            all_captured_envs = []
            call_count = [0]  # Track calls
            def capture_subprocess_run(*args, **kwargs):
                call_count[0] += 1
                print(f"Call {call_count[0]}: args={args}, env keys={list(kwargs.get('env', {}).keys())}")
                if 'env' in kwargs:
                    # Capture a copy of the env
                    env_copy = dict(kwargs['env'])
                    all_captured_envs.append(env_copy)
                result = MagicMock()
                result.returncode = 0
                result.stdout = b'test'
                result.stderr = b''
                return result

            with patch('orchestrator.exec.step_executor.subprocess.run', side_effect=capture_subprocess_run):
                with patch('orchestrator.providers.executor.subprocess.run', side_effect=capture_subprocess_run):
                    try:
                        executor.execute()
                    except Exception as e:
                        print(f"Execution failed: {e}")
                        print(f"Calls made: {call_count[0]}")
                        raise

            # Should have captured 2 envs (one per loop iteration)
            assert len(all_captured_envs) == 2

            # Both iterations should have literal env values
            for env in all_captured_envs:
                assert env['LOOP_VAR'] == '${loop.index}'  # Literal
                assert env['ITEM_VAR'] == '${item}'         # Literal
                assert env['MIXED'] == 'prefix-${steps.X.y}-${loop.total}'  # Literal

    def test_at66_env_empty_and_special_values(self):
        """AT-66: Empty strings and special characters in env should be preserved"""
        workflow = {
            "version": "1.1",
            "steps": [
                {
                    "name": "SpecialEnv",
                    "command": "echo 'test'",
                    "env": {
                        "EMPTY": "",
                        "SPACES": "  ${var}  ",
                        "NEWLINES": "line1\\n${var}\\nline3",
                        "TABS": "\\t${var}\\t",
                        "QUOTES": "'${var}' and \"${var}\"",
                        "ESCAPES": "\\${var} and \\\\${var}"
                    }
                }
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            workflow_file = Path(tmpdir) / "workflow.yaml"
            import yaml
            with open(workflow_file, 'w') as f:
                yaml.dump(workflow, f)

            state_manager = StateManager(workspace=Path(tmpdir), run_id="test-run")
            state_manager.initialize("workflow.yaml")

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=Path(tmpdir),
                state_manager=state_manager
            )

            captured_env = {}
            def capture_subprocess_run(*args, **kwargs):
                if 'env' in kwargs:
                    captured_env.update(kwargs['env'])
                result = MagicMock()
                result.returncode = 0
                result.stdout = b'test'
                result.stderr = b''
                return result

            with patch('orchestrator.exec.step_executor.subprocess.run', side_effect=capture_subprocess_run):
                with patch('orchestrator.providers.executor.subprocess.run', side_effect=capture_subprocess_run):
                    executor.execute()

            # All special values should be preserved literally
            assert captured_env['EMPTY'] == ""
            assert captured_env['SPACES'] == "  ${var}  "
            assert captured_env['NEWLINES'] == "line1\\n${var}\\nline3"
            assert captured_env['TABS'] == "\\t${var}\\t"
            assert captured_env['QUOTES'] == "'${var}' and \"${var}\""
            assert captured_env['ESCAPES'] == "\\${var} and \\\\${var}"