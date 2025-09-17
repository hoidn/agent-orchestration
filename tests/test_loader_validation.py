"""Tests for loader DSL validation per specs/dsl.md and acceptance tests."""

import pytest
import tempfile
import yaml
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError


class TestLoaderValidation:
    """Test strict DSL validation in the loader."""

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

    def test_at7_env_namespace_rejected(self):
        """AT-7: ${env.*} namespace rejected by schema validator."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["echo", "${env.HOME}"]  # Not allowed
            }]
        }

        path = self.write_workflow(workflow)

        # Should raise WorkflowValidationError
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2

        # Verify error message
        assert any("${env.*} namespace not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at7_env_in_provider_params_rejected(self):
        """AT-7: ${env.*} rejected in provider_params."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "providers": {
                "claude": {
                    "command": ["claude", "code"]
                }
            },
            "steps": [{
                "name": "step1",
                "provider": "claude",
                "provider_params": {
                    "model": "${env.MODEL}"  # Not allowed
                }
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("${env.*} namespace not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at10_provider_command_exclusivity(self):
        """AT-10: Provider/Command exclusivity - validation error when both present."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "providers": {
                "claude": {
                    "command": ["claude"]
                }
            },
            "steps": [{
                "name": "invalid_step",
                "provider": "claude",  # Can't have both
                "command": ["echo", "test"]  # Can't have both
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("mutually exclusive" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at36_wait_for_exclusivity(self):
        """AT-36: wait_for cannot be combined with command/provider/for_each."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "invalid_wait",
                "wait_for": {
                    "patterns": ["*.txt"],
                    "timeout_sec": 10
                },
                "command": ["echo", "test"]  # Can't combine with wait_for
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("wait_for cannot be combined" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at38_absolute_path_rejected(self):
        """AT-38: Absolute paths rejected at validation."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["cat"],
                "input_file": "/etc/passwd"  # Absolute path not allowed
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("absolute paths not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at39_parent_escape_rejected(self):
        """AT-39: Parent directory traversal rejected."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["cat"],
                "output_file": "../outside.txt"  # Parent escape not allowed
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("parent directory traversal" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at40_deprecated_override_rejected(self):
        """AT-40: Deprecated command_override usage rejected."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["echo"],
                "command_override": "echo test"  # Deprecated, must reject
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("deprecated 'command_override' not supported" in str(err.message)
                  for err in exc_info.value.errors)

    def test_strict_unknown_fields_rejected(self):
        """Strict validation: unknown fields rejected."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "unknown_field": "value",  # Not a valid field
            "steps": [{
                "name": "step1",
                "command": ["echo", "test"]
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("Unknown field 'unknown_field'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_goto_target_validation(self):
        """Goto targets must exist."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["test", "-f", "file.txt"],
                "on": {
                    "failure": {
                        "goto": "nonexistent_step"  # Must exist
                    }
                }
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("unknown target 'nonexistent_step'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_version_gating_inject_requires_1_1_1(self):
        """depends_on.inject requires version 1.1.1."""
        workflow = {
            "version": "1.1",  # Wrong version
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["echo"],
                "depends_on": {
                    "required": ["file.txt"],
                    "inject": True  # Requires 1.1.1
                }
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("inject requires version '1.1.1'" in str(err.message)
                  for err in exc_info.value.errors)

    # Positive test cases

    def test_valid_minimal_workflow(self):
        """Valid minimal workflow loads successfully."""
        workflow = {
            "version": "1.1",
            "name": "minimal",
            "steps": [{
                "name": "step1",
                "command": ["echo", "hello"]
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        assert result["version"] == "1.1"
        assert result["name"] == "minimal"
        assert len(result["steps"]) == 1

    def test_valid_provider_workflow(self):
        """Valid provider-based workflow."""
        workflow = {
            "version": "1.1",
            "name": "provider test",
            "providers": {
                "claude": {
                    "command": ["claude", "code", "${PROMPT}"],
                    "input_mode": "argv"
                }
            },
            "steps": [{
                "name": "ask_claude",
                "provider": "claude",
                "provider_params": {
                    "model": "claude-3"
                }
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        assert "providers" in result
        assert "claude" in result["providers"]

    def test_valid_for_each_loop(self):
        """Valid for_each loop configuration."""
        workflow = {
            "version": "1.1",
            "name": "loop test",
            "steps": [
                {
                    "name": "list_files",
                    "command": ["ls", "-1"],
                    "output_capture": "lines"
                },
                {
                    "name": "process_files",
                    "for_each": {
                        "items_from": "steps.list_files.lines",
                        "steps": [{
                            "name": "process",
                            "command": ["echo", "${item}"]
                        }]
                    }
                }
            ]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        assert len(result["steps"]) == 2
        assert "for_each" in result["steps"][1]

    def test_valid_variables_usage(self):
        """Valid variable substitution in allowed fields."""
        workflow = {
            "version": "1.1",
            "name": "variables test",
            "context": {
                "project": "test"
            },
            "steps": [{
                "name": "step1",
                "command": ["echo", "${context.project}"],
                "input_file": "${context.project}/input.txt",
                "output_file": "output_${run.id}.txt"
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        # Should load without errors
        assert result["context"]["project"] == "test"

    def test_goto_end_target_valid(self):
        """_end is a valid goto target."""
        workflow = {
            "version": "1.1",
            "name": "goto test",
            "steps": [{
                "name": "step1",
                "command": ["test", "-f", "done.txt"],
                "on": {
                    "success": {
                        "goto": "_end"  # Reserved target
                    }
                }
            }, {
                "name": "step2",
                "command": ["echo", "not reached"]
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        # Should load without errors
        assert len(result["steps"]) == 2