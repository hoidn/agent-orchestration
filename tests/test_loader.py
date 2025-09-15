"""Unit tests for workflow loader - validates AT-7, AT-10, AT-38/39, AT-40, AT-48/49, AT-28"""

import pytest
import tempfile
from pathlib import Path
import yaml

from orchestrator.workflow.loader import WorkflowLoader, ValidationError
from orchestrator.workflow.types import DSLVersion, OutputCapture


class TestWorkflowLoader:
    """Test workflow loading and validation"""

    def setup_method(self):
        """Setup test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.loader = WorkflowLoader(self.workspace)

    def write_workflow(self, content: dict) -> Path:
        """Helper to write workflow YAML"""
        workflow_path = self.workspace / "test_workflow.yaml"
        with open(workflow_path, 'w') as f:
            yaml.dump(content, f)
        return workflow_path

    # AT-7: Unknown fields rejected
    def test_unknown_workflow_fields_rejected(self):
        """AT-7: Unknown fields in workflow are rejected"""
        workflow_data = {
            'version': '1.1',
            'name': 'test',
            'unknown_field': 'value',  # Should cause error
            'steps': [
                {'name': 'step1', 'command': ['echo', 'test']}
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "Unknown fields in workflow" in str(exc.value)
        assert "unknown_field" in str(exc.value)

    def test_unknown_step_fields_rejected(self):
        """AT-7: Unknown fields in steps are rejected"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'step1',
                    'command': ['echo', 'test'],
                    'unknown_step_field': 'value'  # Should cause error
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "Unknown fields in step" in str(exc.value)
        assert "unknown_step_field" in str(exc.value)

    # AT-10: Provider/Command exclusivity
    def test_provider_command_mutual_exclusivity(self):
        """AT-10: Step with both provider and command is rejected"""
        workflow_data = {
            'version': '1.1',
            'providers': {
                'claude': {
                    'command': ['claude', '-p', '${PROMPT}']
                }
            },
            'steps': [
                {
                    'name': 'invalid_step',
                    'provider': 'claude',  # Has provider
                    'command': ['echo', 'test']  # Also has command - invalid!
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "multiple execution types" in str(exc.value)
        assert "provider" in str(exc.value)
        assert "command" in str(exc.value)

    def test_wait_for_exclusivity(self):
        """AT-36: wait_for cannot be combined with other execution types"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'invalid_wait',
                    'wait_for': {'glob': '*.txt'},
                    'command': ['echo', 'test']  # Can't combine with wait_for
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "multiple execution types" in str(exc.value)

    # AT-38/39: Path safety
    def test_absolute_path_rejected(self):
        """AT-38: Absolute paths are rejected"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'abs_path_step',
                    'command': ['cat', 'file.txt'],
                    'input_file': '/etc/passwd'  # Absolute path - invalid!
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "absolute path" in str(exc.value)
        assert "/etc/passwd" in str(exc.value)

    def test_parent_escape_rejected(self):
        """AT-39: Paths with .. are rejected"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'parent_escape',
                    'command': ['cat', 'file.txt'],
                    'output_file': '../../../etc/passwd'  # Parent escape - invalid!
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "contains '..'" in str(exc.value)

    def test_dependency_path_safety(self):
        """AT-39: Dependencies with unsafe paths are rejected"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'dep_step',
                    'command': ['echo', 'test'],
                    'depends_on': {
                        'required': ['/absolute/path.txt', '../escape.txt']
                    }
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "absolute path" in str(exc.value) or "contains '..'" in str(exc.value)

    # AT-40: Deprecated fields
    def test_command_override_rejected(self):
        """AT-40: Deprecated command_override field is rejected"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'deprecated_step',
                    'command': ['echo', 'test'],
                    'command_override': ['other', 'command']  # Deprecated!
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "deprecated 'command_override'" in str(exc.value)

    # AT-28: Version gating for inject
    def test_inject_requires_version_1_1_1(self):
        """AT-28: Using inject with version 1.1 is rejected"""
        workflow_data = {
            'version': '1.1',  # Wrong version for inject!
            'steps': [
                {
                    'name': 'inject_step',
                    'command': ['echo', 'test'],
                    'depends_on': {
                        'required': ['file.txt'],
                        'inject': True  # Requires v1.1.1
                    }
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "inject" in str(exc.value)
        assert "requires version 1.1.1" in str(exc.value)

    def test_inject_allowed_with_version_1_1_1(self):
        """AT-28: inject is allowed with version 1.1.1"""
        workflow_data = {
            'version': '1.1.1',  # Correct version for inject
            'steps': [
                {
                    'name': 'inject_step',
                    'command': ['echo', 'test'],
                    'depends_on': {
                        'required': ['file.txt'],
                        'inject': True  # Now allowed
                    }
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        workflow = self.loader.load(workflow_path)

        assert workflow.dsl_version == DSLVersion.V1_1_1
        step = workflow.steps[0]
        assert step.depends_on.inject is not None
        assert step.depends_on.inject.mode == 'list'  # Default
        assert step.depends_on.inject.position == 'prepend'  # Default

    def test_inject_object_form(self):
        """AT-29/30/31: inject object form with custom settings"""
        workflow_data = {
            'version': '1.1.1',
            'steps': [
                {
                    'name': 'custom_inject',
                    'command': ['echo', 'test'],
                    'depends_on': {
                        'required': ['*.md'],
                        'inject': {
                            'mode': 'content',
                            'instruction': 'Custom instruction',
                            'position': 'append'
                        }
                    }
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        workflow = self.loader.load(workflow_path)

        step = workflow.steps[0]
        assert step.depends_on.inject.mode == 'content'
        assert step.depends_on.inject.instruction == 'Custom instruction'
        assert step.depends_on.inject.position == 'append'

    # Goto validation
    def test_goto_target_validation(self):
        """Goto targets must exist or be _end"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'step1',
                    'command': ['echo', 'test'],
                    'on': {
                        'success': {'goto': 'nonexistent_step'}  # Invalid target
                    }
                },
                {
                    'name': 'step2',
                    'command': ['echo', 'test2']
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "unknown target" in str(exc.value)
        assert "nonexistent_step" in str(exc.value)

    def test_goto_end_allowed(self):
        """_end is always a valid goto target"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'step1',
                    'command': ['echo', 'test'],
                    'on': {
                        'success': {'goto': '_end'}  # Valid special target
                    }
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        workflow = self.loader.load(workflow_path)

        assert workflow.steps[0].on.success.goto == '_end'

    # Valid workflow examples
    def test_valid_minimal_workflow(self):
        """A minimal valid workflow loads successfully"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {'name': 'simple', 'command': ['echo', 'hello']}
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        workflow = self.loader.load(workflow_path)

        assert workflow.version == '1.1'
        assert len(workflow.steps) == 1
        assert workflow.steps[0].name == 'simple'
        assert workflow.steps[0].command == ['echo', 'hello']
        assert workflow.strict_flow is True  # Default

    def test_provider_workflow(self):
        """Provider-based workflow loads correctly"""
        workflow_data = {
            'version': '1.1',
            'providers': {
                'claude': {
                    'command': ['claude', '-p', '${PROMPT}', '--model', '${model}'],
                    'defaults': {'model': 'claude-3'},
                    'input_mode': 'argv'
                }
            },
            'steps': [
                {
                    'name': 'ask_claude',
                    'provider': 'claude',
                    'provider_params': {'model': 'claude-3.5'},
                    'input_file': 'prompt.txt'
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        workflow = self.loader.load(workflow_path)

        assert 'claude' in workflow.providers
        provider = workflow.providers['claude']
        assert provider.command == ['claude', '-p', '${PROMPT}', '--model', '${model}']
        assert provider.defaults == {'model': 'claude-3'}

        step = workflow.steps[0]
        assert step.provider == 'claude'
        assert step.provider_params == {'model': 'claude-3.5'}

    def test_for_each_workflow(self):
        """for_each loops parse correctly"""
        workflow_data = {
            'version': '1.1',
            'steps': [
                {
                    'name': 'list_files',
                    'command': ['ls'],
                    'output_capture': 'lines'
                },
                {
                    'name': 'process_files',
                    'for_each': {
                        'items_from': 'steps.list_files.lines',
                        'as': 'file',
                        'steps': [
                            {
                                'name': 'process',
                                'command': ['cat', '${file}']
                            }
                        ]
                    }
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        workflow = self.loader.load(workflow_path)

        assert workflow.steps[0].output_capture == OutputCapture.LINES

        loop_step = workflow.steps[1]
        assert loop_step.for_each is not None
        assert loop_step.for_each.items_from == 'steps.list_files.lines'
        assert loop_step.for_each.as_var == 'file'
        assert len(loop_step.for_each.steps) == 1

    def test_json_validation_requires_v1_3(self):
        """JSON output validation requires version 1.3"""
        workflow_data = {
            'version': '1.1',  # Wrong version
            'steps': [
                {
                    'name': 'json_step',
                    'command': ['echo', '{}'],
                    'output_capture': 'json',
                    'output_require': [  # Requires v1.3
                        {'pointer': '/status', 'exists': True}
                    ]
                }
            ]
        }

        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)

        assert "output_require" in str(exc.value)
        assert "version 1.3" in str(exc.value)

    def test_missing_required_fields(self):
        """Missing required fields are caught"""
        # Missing version
        workflow_data = {
            'steps': [{'name': 'step1', 'command': ['echo']}]
        }
        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)
        assert "must specify 'version'" in str(exc.value)

        # Missing step name
        workflow_data = {
            'version': '1.1',
            'steps': [{'command': ['echo']}]  # No name
        }
        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)
        assert "must have 'name'" in str(exc.value)

        # Empty steps
        workflow_data = {
            'version': '1.1',
            'steps': []
        }
        workflow_path = self.write_workflow(workflow_data)
        with pytest.raises(ValidationError) as exc:
            self.loader.load(workflow_path)
        assert "at least one step" in str(exc.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])