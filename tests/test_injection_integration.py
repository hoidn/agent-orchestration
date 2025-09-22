"""
Integration tests for dependency injection with debug record.
Acceptance tests: AT-28-35, AT-53
"""

import pytest
import yaml
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import json

from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.exceptions import WorkflowValidationError


def create_workflow_file(workspace: Path, workflow: dict, filename: str = "test.yaml") -> str:
    """Helper to create workflow file on disk for StateManager."""
    workflow_path = workspace / filename
    with open(workflow_path, 'w') as f:
        yaml.dump(workflow, f)
    return filename


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "artifacts").mkdir()
        (workspace / "artifacts/architect").mkdir()
        (workspace / "prompts").mkdir()
        (workspace / "processed").mkdir()
        (workspace / ".orchestrate").mkdir()
        (workspace / ".orchestrate/runs").mkdir()
        yield workspace


@pytest.fixture
def mock_provider_registry():
    """Mock provider registry with test provider."""
    from orchestrator.providers.registry import ProviderRegistry
    from orchestrator.providers.types import ProviderTemplate, InputMode

    registry = ProviderRegistry()
    template = ProviderTemplate(
        name="claude",
        command=["claude", "--model", "${model}", "-p", "${PROMPT}"],
        defaults={"model": "claude-sonnet"},
        input_mode=InputMode.ARGV
    )
    registry._providers["claude"] = template
    return registry


def test_at28_basic_injection(temp_workspace, mock_provider_registry):
    """AT-28: Basic injection with inject: true prepends default instruction + file list."""
    # Create test files
    (temp_workspace / "artifacts/architect/design.md").write_text("Design document")
    (temp_workspace / "artifacts/architect/api.md").write_text("API specification")
    (temp_workspace / "prompts/implement.md").write_text("Please implement the feature")

    # Create workflow with basic injection
    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "test_step",
                "provider": "claude",
                "input_file": "prompts/implement.md",
                "depends_on": {
                    "required": ["artifacts/architect/*.md"],
                    "inject": True  # Shorthand for list mode, prepend
                }
            }
        ]
    }

    # Mock provider execution
    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=b"Success",
                stderr=b""
            )

            # Write workflow to file for state manager
            workflow_file = temp_workspace / 'test_workflow.yaml'
            workflow_file.write_text(yaml.dump(workflow))

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow, 'test_workflow.yaml')
            state_manager = StateManager(temp_workspace)

            # Initialize state
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            # Verify provider was called with injected prompt
            call_args = mock_run.call_args
            assert call_args is not None

            # Check that the command includes the PROMPT placeholder substitution
            command = call_args[0][0]
            assert "claude" in command
            assert "--model" in command

            # Find the prompt argument (after -p)
            p_index = command.index("-p")
            injected_prompt = command[p_index + 1]

            # Verify injection structure
            assert "The following required files are available:" in injected_prompt
            assert "- artifacts/architect/api.md" in injected_prompt
            assert "- artifacts/architect/design.md" in injected_prompt
            assert "Please implement the feature" in injected_prompt

            # Files should be in lexicographic order
            api_pos = injected_prompt.index("api.md")
            design_pos = injected_prompt.index("design.md")
            assert api_pos < design_pos


def test_at29_list_mode_injection(temp_workspace, mock_provider_registry):
    """AT-29: List mode injection correctly lists all resolved file paths."""
    # Create multiple test files
    files = ["doc1.md", "doc2.md", "doc3.md"]
    for f in files:
        (temp_workspace / f).write_text(f"Content of {f}")

    (temp_workspace / "prompts/task.md").write_text("Task prompt")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "list_test",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["*.md"],
                    "inject": {
                        "mode": "list",
                        "instruction": "Available documentation:",
                        "position": "prepend"
                    }
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            injected = command[p_index + 1]

            # Verify custom instruction
            assert "Available documentation:" in injected
            # All files should be listed
            for f in files:
                assert f"- {f}" in injected
            # Original prompt should follow
            assert "Task prompt" in injected


def test_at30_content_mode_injection(temp_workspace, mock_provider_registry):
    """AT-30: Content mode includes file contents with truncation metadata."""
    # Create test file with content
    (temp_workspace / "data.txt").write_text("This is the data content\nWith multiple lines")
    (temp_workspace / "prompts/analyze.md").write_text("Analyze this data")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "content_test",
                "provider": "claude",
                "input_file": "prompts/analyze.md",
                "depends_on": {
                    "required": ["data.txt"],
                    "inject": {
                        "mode": "content",
                        "position": "prepend"
                    }
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            injected = command[p_index + 1]

            # Verify content mode format
            assert "=== File: data.txt" in injected
            assert "bytes) ===" in injected
            assert "This is the data content" in injected
            assert "With multiple lines" in injected
            assert "Analyze this data" in injected


def test_at31_custom_instruction(temp_workspace, mock_provider_registry):
    """AT-31: Custom instruction overrides default text."""
    (temp_workspace / "spec.md").write_text("Specification")
    (temp_workspace / "prompts/impl.md").write_text("Implementation task")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "custom_instruction",
                "provider": "claude",
                "input_file": "prompts/impl.md",
                "depends_on": {
                    "required": ["spec.md"],
                    "inject": {
                        "mode": "list",
                        "instruction": "You must follow these specs precisely:",
                        "position": "prepend"
                    }
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            injected = command[p_index + 1]

            # Custom instruction should be used
            assert "You must follow these specs precisely:" in injected
            # Default instruction should not appear
            assert "The following required files" not in injected


def test_at32_append_position(temp_workspace, mock_provider_registry):
    """AT-32: Append position places injection after prompt content."""
    (temp_workspace / "ref.txt").write_text("Reference material")
    (temp_workspace / "prompts/main.md").write_text("Main task description")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "append_test",
                "provider": "claude",
                "input_file": "prompts/main.md",
                "depends_on": {
                    "optional": ["ref.txt"],
                    "inject": {
                        "mode": "list",
                        "instruction": "Additional references:",
                        "position": "append"
                    }
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            injected = command[p_index + 1]

            # Main prompt should come first
            main_pos = injected.index("Main task description")
            ref_pos = injected.index("Additional references:")
            assert main_pos < ref_pos


def test_at33_pattern_injection(temp_workspace, mock_provider_registry):
    """AT-33: Glob patterns resolve to full list before injection."""
    # Create multiple matching files
    (temp_workspace / "docs").mkdir()
    for i in range(3):
        (temp_workspace / f"docs/guide{i}.md").write_text(f"Guide {i}")

    (temp_workspace / "prompts/task.md").write_text("Task")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "pattern_test",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["docs/*.md"],
                    "inject": True
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            injected = command[p_index + 1]

            # All matching files should be listed
            assert "- docs/guide0.md" in injected
            assert "- docs/guide1.md" in injected
            assert "- docs/guide2.md" in injected


def test_at34_optional_file_injection(temp_workspace, mock_provider_registry):
    """AT-34: Missing optional files omitted from injection without error."""
    # Only create one of two optional files
    (temp_workspace / "exists.txt").write_text("This file exists")
    # missing.txt does not exist
    (temp_workspace / "prompts/task.md").write_text("Task")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "optional_test",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "optional": ["exists.txt", "missing.txt"],
                    "inject": {
                        "mode": "list",
                        "instruction": "Optional files:"
                    }
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            # Should succeed despite missing optional file
            assert state['steps']['optional_test']['status'] == 'completed'

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            injected = command[p_index + 1]

            # Only existing file should be listed
            assert "- exists.txt" in injected
            assert "missing.txt" not in injected


def test_at35_no_injection_default(temp_workspace, mock_provider_registry):
    """AT-35: Without inject field, prompt unchanged."""
    (temp_workspace / "required.txt").write_text("Required file")
    (temp_workspace / "prompts/task.md").write_text("Original task prompt")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "no_inject",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["required.txt"]
                    # No inject field
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            command = mock_run.call_args[0][0]
            p_index = command.index("-p")
            prompt = command[p_index + 1]

            # Prompt should be unchanged
            assert prompt == "Original task prompt"
            # No injection content
            assert "required.txt" not in prompt
            assert "files are available" not in prompt


def test_at53_injection_shorthand(temp_workspace, mock_provider_registry):
    """AT-53: inject:true shorthand equals {mode:list, position:prepend}."""
    (temp_workspace / "spec.txt").write_text("Spec")
    (temp_workspace / "prompts/task.md").write_text("Task")

    # Test with shorthand
    workflow1 = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "shorthand",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["spec.txt"],
                    "inject": True
                }
            }
        ]
    }

    # Test with explicit config
    workflow2 = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "explicit",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["spec.txt"],
                    "inject": {
                        "mode": "list",
                        "position": "prepend"
                    }
                }
            }
        ]
    }

    injected_prompts = []

    for i, workflow in enumerate([workflow1, workflow2]):
        with patch.object(mock_provider_registry, 'get') as mock_get:
            mock_get.return_value = mock_provider_registry._providers['claude']

            with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

                # Create workflow file and state manager
                workflow_file = create_workflow_file(temp_workspace, workflow, f"test_{i}.yaml")
                state_manager = StateManager(temp_workspace)
                state_manager.initialize(workflow_file, {})

                executor = WorkflowExecutor(
                    workflow=workflow,
                    workspace=temp_workspace,
                    state_manager=state_manager
                )

                # Override provider registry
                executor.provider_registry = mock_provider_registry

                state = executor.execute()

                command = mock_run.call_args[0][0]
                p_index = command.index("-p")
                injected_prompts.append(command[p_index + 1])

    # Both forms should produce identical results
    assert injected_prompts[0] == injected_prompts[1]
    assert "The following required files are available:" in injected_prompts[0]
    assert "- spec.txt" in injected_prompts[0]
    assert injected_prompts[0].startswith("The following")  # Prepend position


def test_injection_truncation_debug_record(temp_workspace, mock_provider_registry):
    """Test that truncation metadata is recorded in debug.injection."""
    # Create a large file that will trigger truncation
    large_content = "x" * (300 * 1024)  # 300KB, over the 256KB limit
    (temp_workspace / "large.txt").write_text(large_content)
    (temp_workspace / "prompts/task.md").write_text("Task")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "truncation_test",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["large.txt"],
                    "inject": {
                        "mode": "content"
                    }
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        with patch('orchestrator.providers.executor.subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout=b"OK", stderr=b"")

            # Create workflow file and state manager
            workflow_file = create_workflow_file(temp_workspace, workflow)
            state_manager = StateManager(temp_workspace)
            state_manager.initialize(workflow_file, {})

            # Execute workflow
            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=temp_workspace,
                state_manager=state_manager
            )

            # Override provider registry
            executor.provider_registry = mock_provider_registry

            state = executor.execute()

            # Check that truncation was recorded in debug
            step_result = state['steps']['truncation_test']
            assert 'debug' in step_result
            assert 'injection' in step_result['debug']

            injection_debug = step_result['debug']['injection']
            assert injection_debug['injection_truncated'] == True
            assert 'truncation_details' in injection_debug

            details = injection_debug['truncation_details']
            assert details['total_size'] > 256 * 1024
            assert details['shown_size'] <= 256 * 1024
            assert details['files_shown'] >= 0
            assert details['files_truncated'] >= 0


def test_dependency_validation_with_injection(temp_workspace, mock_provider_registry):
    """Test that missing required dependencies fail with exit 2."""
    (temp_workspace / "prompts/task.md").write_text("Task")

    workflow = {
        "version": "1.1.1",
        "steps": [
            {
                "name": "missing_deps",
                "provider": "claude",
                "input_file": "prompts/task.md",
                "depends_on": {
                    "required": ["missing/*.txt"],
                    "inject": True
                }
            }
        ]
    }

    with patch.object(mock_provider_registry, 'get') as mock_get:
        mock_get.return_value = mock_provider_registry._providers['claude']

        # Create workflow file and state manager
        workflow_file = create_workflow_file(temp_workspace, workflow)
        state_manager = StateManager(temp_workspace)
        state_manager.initialize(workflow_file, {})

        executor = WorkflowExecutor(
            workflow=workflow,
            workspace=temp_workspace,
            state_manager=state_manager
        )

        # Override provider registry
        executor.provider_registry = mock_provider_registry

        state = executor.execute()

        # Should fail with exit code 2
        step_result = state['steps']['missing_deps']
        assert step_result['status'] == 'failed'
        assert step_result['exit_code'] == 2
        assert 'error' in step_result
        assert step_result['error']['type'] == 'dependency_validation'