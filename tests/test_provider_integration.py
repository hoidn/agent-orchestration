"""
Integration tests for provider functionality with loader and executor.

Tests the complete pipeline from workflow definition to provider execution.
"""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrator.loader import WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers import ProviderRegistry, ProviderExecutor
from orchestrator.exec.step_executor import StepExecutor


class TestProviderIntegration:
    """Test provider integration with workflow loader and executor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.loader = WorkflowLoader(self.workspace)

    def write_workflow(self, content: dict) -> Path:
        """Helper to write workflow YAML."""
        path = self.workspace / "workflow.yml"
        with open(path, 'w') as f:
            yaml.dump(content, f)
        return path

    def test_at8_provider_workflow_loading(self):
        """AT-8: Provider templates load and validate correctly."""
        workflow = {
            "version": "1.1",
            "name": "provider_test",
            "providers": {
                "custom": {
                    "command": ["custom-cli", "-p", "${PROMPT}", "--model", "${model}"],
                    "defaults": {
                        "model": "default-model"
                    },
                    "input_mode": "argv"
                }
            },
            "steps": [{
                "name": "UseProvider",
                "provider": "custom",
                "provider_params": {
                    "model": "override-model"
                },
                "input_file": "prompt.txt"
            }]
        }

        # Create prompt file
        (self.workspace / "prompt.txt").write_text("Test prompt")

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        assert loaded is not None
        assert "custom" in loaded["providers"]

        # Check provider was parsed correctly
        custom = loaded["providers"]["custom"]
        assert custom["command"] == ["custom-cli", "-p", "${PROMPT}", "--model", "${model}"]
        assert custom["defaults"]["model"] == "default-model"
        assert custom.get("input_mode", "argv") == "argv"

    def test_at9_stdin_mode_workflow(self):
        """AT-9: stdin mode provider in workflow."""
        workflow = {
            "version": "1.1",
            "name": "stdin_test",
            "providers": {
                "stdin_tool": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "defaults": {
                        "model": "test"
                    }
                }
            },
            "steps": [{
                "name": "StdinStep",
                "provider": "stdin_tool",
                "input_file": "input.txt"
            }]
        }

        (self.workspace / "input.txt").write_text("Input for stdin")
        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        assert loaded is not None
        provider = loaded["providers"]["stdin_tool"]
        assert provider["input_mode"] == "stdin"

    def test_at49_stdin_prompt_validation_in_workflow(self):
        """AT-49: stdin mode with ${PROMPT} fails validation."""
        workflow = {
            "version": "1.1",
            "name": "invalid_stdin",
            "providers": {
                "bad_stdin": {
                    "command": ["tool", "-p", "${PROMPT}"],  # Invalid in stdin
                    "input_mode": "stdin"
                }
            },
            "steps": [{
                "name": "BadStep",
                "provider": "bad_stdin"
            }]
        }

        path = self.write_workflow(workflow)

        # Should fail validation
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        # Check error mentions the issue
        assert any("${PROMPT} not allowed in stdin mode" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at50_provider_without_prompt_placeholder(self):
        """AT-50: Provider without ${PROMPT} works correctly."""
        workflow = {
            "version": "1.1",
            "name": "no_prompt",
            "providers": {
                "simple": {
                    "command": ["simple-tool", "--config", "${config}"],
                    "defaults": {
                        "config": "/etc/config.yml"
                    }
                }
            },
            "steps": [{
                "name": "SimpleStep",
                "provider": "simple",
                "provider_params": {
                    "config": "/custom/config.yml"
                }
            }]
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        assert loaded is not None
        step = loaded["steps"][0]
        assert step["provider"] == "simple"
        assert step["provider_params"]["config"] == "/custom/config.yml"

    def test_at51_provider_params_with_variables(self):
        """AT-51: Provider params support variable substitution."""
        workflow = {
            "version": "1.1",
            "name": "param_vars",
            "context": {
                "base_path": "/workspace"
            },
            "providers": {
                "tool": {
                    "command": ["tool", "--input", "${input_path}", "--output", "${output_path}"]
                }
            },
            "steps": [{
                "name": "VarStep",
                "provider": "tool",
                "provider_params": {
                    "input_path": "${context.base_path}/input.txt",
                    "output_path": "${context.base_path}/output.txt"
                }
            }]
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        assert loaded is not None
        step = loaded["steps"][0]
        # Variables in provider_params should be preserved for runtime substitution
        assert "${context.base_path}" in step["provider_params"]["input_path"]

    @patch('subprocess.run')
    def test_complete_provider_execution_flow(self, mock_run):
        """Test complete flow from workflow to execution."""
        # Create workflow with provider
        workflow = {
            "version": "1.1",
            "name": "full_test",
            "providers": {
                "test_cli": {
                    "command": ["test-cli", "-p", "${PROMPT}", "--model", "${model}"],
                    "defaults": {
                        "model": "base-model"
                    }
                }
            },
            "steps": [{
                "name": "TestStep",
                "provider": "test_cli",
                "provider_params": {
                    "model": "custom-model"
                },
                "input_file": "prompt.md",
                "output_file": "output.txt"
            }]
        }

        # Create prompt file
        prompt_file = self.workspace / "prompt.md"
        prompt_file.write_text("Execute this task")

        # Load workflow
        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        # Set up provider registry and executor
        registry = ProviderRegistry()
        registry.register_from_workflow(loaded["providers"])
        executor = ProviderExecutor(self.workspace, registry)

        # Get step and prepare invocation
        step = loaded["steps"][0]
        params = {
            "params": step.get("provider_params", {}),
            "input_file": step.get("input_file"),
            "output_file": step.get("output_file")
        }

        # Read prompt content
        prompt_content = prompt_file.read_text()

        # Prepare invocation
        from orchestrator.providers import ProviderParams
        provider_params = ProviderParams(**params)
        invocation, error = executor.prepare_invocation(
            step["provider"],
            provider_params,
            {},  # context
            prompt_content
        )

        assert error is None
        assert invocation is not None

        # Verify command was built correctly
        command_str = " ".join(invocation.command)
        assert "Execute this task" in command_str
        assert "custom-model" in command_str  # Step param overrides default

        # Mock successful execution
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"Task completed",
            stderr=b""
        )

        # Execute
        result = executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"Task completed"

    def test_builtin_providers_available(self):
        """Test that built-in providers work without workflow definition."""
        workflow = {
            "version": "1.1",
            "name": "builtin_test",
            "steps": [
                {
                    "name": "UseClaude",
                    "provider": "claude",  # Built-in provider
                    "input_file": "prompt.txt"
                },
                {
                    "name": "UseCodex",
                    "provider": "codex",  # Built-in stdin provider
                    "input_file": "prompt.txt"
                }
            ]
        }

        (self.workspace / "prompt.txt").write_text("Test")
        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        assert loaded is not None
        # Built-in providers should work without explicit definition
        assert loaded["steps"][0]["provider"] == "claude"
        assert loaded["steps"][1]["provider"] == "codex"