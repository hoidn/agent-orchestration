"""
Test suite for conditional execution (when.equals/exists/not_exists).
Tests AT-37, AT-46, AT-47.
"""

import json
import os
import tempfile
from pathlib import Path
import pytest

from orchestrator.workflow.conditions import ConditionEvaluator
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.loader import WorkflowLoader


class TestConditionEvaluator:
    """Test the ConditionEvaluator class directly."""

    def test_no_condition_always_true(self):
        """No condition means always execute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))
            assert evaluator.evaluate(None, {}) is True

    def test_at37_equals_condition_true(self):
        """AT-37: when.equals with matching values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))
            condition = {
                'equals': {
                    'left': 'hello',
                    'right': 'hello'
                }
            }
            assert evaluator.evaluate(condition, {}) is True

    def test_at37_equals_condition_false(self):
        """AT-37: when.equals with different values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))
            condition = {
                'equals': {
                    'left': 'hello',
                    'right': 'world'
                }
            }
            assert evaluator.evaluate(condition, {}) is False

    def test_at37_equals_with_variables(self):
        """AT-37: when.equals with variable substitution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))
            condition = {
                'equals': {
                    'left': '${context.env}',
                    'right': 'production'
                }
            }
            variables = {
                'context': {'env': 'production'}
            }
            assert evaluator.evaluate(condition, variables) is True

            # Different value
            variables['context']['env'] = 'development'
            assert evaluator.evaluate(condition, variables) is False

    def test_at46_exists_condition_true(self):
        """AT-46: when.exists true when files match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            evaluator = ConditionEvaluator(workspace)

            # Create test files
            (workspace / 'test.txt').write_text('hello')
            (workspace / 'data.json').write_text('{}')

            # Single file exists
            condition = {'exists': 'test.txt'}
            assert evaluator.evaluate(condition, {}) is True

            # Glob pattern matches
            condition = {'exists': '*.txt'}
            assert evaluator.evaluate(condition, {}) is True

            # Multiple matches
            condition = {'exists': '*'}
            assert evaluator.evaluate(condition, {}) is True

    def test_at46_exists_condition_false(self):
        """AT-46: when.exists false when no files match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            evaluator = ConditionEvaluator(workspace)

            # No files exist
            condition = {'exists': 'missing.txt'}
            assert evaluator.evaluate(condition, {}) is False

            # No matches for glob
            condition = {'exists': '*.py'}
            assert evaluator.evaluate(condition, {}) is False

    def test_at47_not_exists_condition_true(self):
        """AT-47: when.not_exists true when no files match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            evaluator = ConditionEvaluator(workspace)

            # File doesn't exist
            condition = {'not_exists': 'missing.txt'}
            assert evaluator.evaluate(condition, {}) is True

            # Create a file
            (workspace / 'test.txt').write_text('hello')

            # Different file still doesn't exist
            condition = {'not_exists': 'other.txt'}
            assert evaluator.evaluate(condition, {}) is True

            # No .py files
            condition = {'not_exists': '*.py'}
            assert evaluator.evaluate(condition, {}) is True

    def test_at47_not_exists_condition_false(self):
        """AT-47: when.not_exists false when files match."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            evaluator = ConditionEvaluator(workspace)

            # Create test file
            (workspace / 'test.txt').write_text('hello')

            # File exists
            condition = {'not_exists': 'test.txt'}
            assert evaluator.evaluate(condition, {}) is False

            # Glob matches
            condition = {'not_exists': '*.txt'}
            assert evaluator.evaluate(condition, {}) is False

    def test_exists_with_directories(self):
        """when.exists should work with directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            evaluator = ConditionEvaluator(workspace)

            # Create directory
            (workspace / 'mydir').mkdir()

            condition = {'exists': 'mydir'}
            assert evaluator.evaluate(condition, {}) is True

            condition = {'not_exists': 'mydir'}
            assert evaluator.evaluate(condition, {}) is False

    def test_path_safety_in_conditions(self):
        """Conditions should reject unsafe paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            evaluator = ConditionEvaluator(workspace)

            # Absolute path should be rejected
            condition = {'exists': '/etc/passwd'}
            with pytest.raises(ValueError, match="Unsafe path"):
                evaluator.evaluate(condition, {})

            # Parent traversal should be rejected
            condition = {'exists': '../etc/passwd'}
            with pytest.raises(ValueError, match="Unsafe path"):
                evaluator.evaluate(condition, {})

    def test_invalid_condition_format(self):
        """Invalid condition formats should raise errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))

            # No condition type
            with pytest.raises(ValueError, match="No valid condition type"):
                evaluator.evaluate({}, {})

            # Multiple condition types
            with pytest.raises(ValueError, match="Multiple condition types"):
                evaluator.evaluate({'equals': {}, 'exists': 'file'}, {})

            # Invalid equals format
            with pytest.raises(ValueError, match="must have 'left' and 'right'"):
                evaluator.evaluate({'equals': {'left': 'val'}}, {})

    def test_type_coercion_in_equals(self):
        """Values should be coerced to strings for comparison."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))

            # Number to string
            condition = {
                'equals': {
                    'left': '${steps.count.exit_code}',
                    'right': '0'
                }
            }
            variables = {
                'steps': {'count': {'exit_code': 0}}
            }
            assert evaluator.evaluate(condition, variables) is True

            # Boolean to string
            condition = {
                'equals': {
                    'left': '${context.enabled}',
                    'right': 'true'
                }
            }
            variables = {
                'context': {'enabled': True}
            }
            assert evaluator.evaluate(condition, variables) is True

            variables['context']['enabled'] = False
            condition['equals']['right'] = 'false'
            assert evaluator.evaluate(condition, variables) is True


class TestWorkflowConditionalExecution:
    """Test conditional execution within workflows."""

    def test_at37_conditional_skip_when_false(self):
        """AT-37: False when condition -> step skipped with exit_code 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create workflow with conditional step
            workflow_yaml = """
version: "1.1"
name: "Conditional Test"
steps:
  - name: ConditionalStep
    command: ["echo", "Should not run"]
    when:
      equals:
        left: "skip"
        right: "execute"
"""
            workflow_file = workspace / 'workflow.yaml'
            workflow_file.write_text(workflow_yaml)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(str(workflow_file))

            state_dir = workspace / '.orchestrate' / 'test_run'
            state_dir.mkdir(parents=True)
            state_manager = StateManager(state_dir)
            state_manager.initialize(str(workflow_file))

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager
            )

            # Execute
            state = executor.execute()

            # Verify step was skipped
            assert 'steps' in state
            assert 'ConditionalStep' in state['steps']
            step_result = state['steps']['ConditionalStep']
            assert step_result['status'] == 'skipped'
            assert step_result['exit_code'] == 0
            assert step_result.get('skipped') is True

    def test_at37_conditional_execute_when_true(self):
        """AT-37: True when condition -> step executes normally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create workflow with conditional step
            workflow_yaml = """
version: "1.1"
name: "Conditional Test"
steps:
  - name: ConditionalStep
    command: ["echo", "Should run"]
    when:
      equals:
        left: "execute"
        right: "execute"
"""
            workflow_file = workspace / 'workflow.yaml'
            workflow_file.write_text(workflow_yaml)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(str(workflow_file))

            state_dir = workspace / '.orchestrate' / 'test_run'
            state_dir.mkdir(parents=True)
            state_manager = StateManager(state_dir)
            state_manager.initialize(str(workflow_file))

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager
            )

            # Execute
            state = executor.execute()

            # Verify step executed
            assert 'steps' in state
            assert 'ConditionalStep' in state['steps']
            step_result = state['steps']['ConditionalStep']
            assert step_result['exit_code'] == 0
            assert step_result.get('skipped') is not True
            assert 'output' in step_result  # Command was executed

    def test_at46_when_exists_in_workflow(self):
        """AT-46: when.exists condition in workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a test file
            (workspace / 'data.txt').write_text('test data')

            # Create workflow with exists condition
            workflow_yaml = """
version: "1.1"
name: "Exists Test"
steps:
  - name: CheckExists
    command: ["echo", "File exists"]
    when:
      exists: "data.txt"
  - name: CheckMissing
    command: ["echo", "Should skip"]
    when:
      exists: "missing.txt"
"""
            workflow_file = workspace / 'workflow.yaml'
            workflow_file.write_text(workflow_yaml)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(str(workflow_file))

            state_dir = workspace / '.orchestrate' / 'test_run'
            state_dir.mkdir(parents=True)
            state_manager = StateManager(state_dir)
            state_manager.initialize(str(workflow_file))

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager
            )

            # Execute
            state = executor.execute()

            # First step should execute
            assert state['steps']['CheckExists']['exit_code'] == 0
            assert 'output' in state['steps']['CheckExists']

            # Second step should be skipped
            assert state['steps']['CheckMissing']['status'] == 'skipped'
            assert state['steps']['CheckMissing']['exit_code'] == 0
            assert state['steps']['CheckMissing'].get('skipped') is True

    def test_at47_when_not_exists_in_workflow(self):
        """AT-47: when.not_exists condition in workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create a test file
            (workspace / 'existing.txt').write_text('test data')

            # Create workflow with not_exists condition
            workflow_yaml = """
version: "1.1"
name: "Not Exists Test"
steps:
  - name: CheckNotExists
    command: ["echo", "Lock not present"]
    when:
      not_exists: "*.lock"
  - name: CheckExists
    command: ["echo", "Should skip"]
    when:
      not_exists: "existing.txt"
"""
            workflow_file = workspace / 'workflow.yaml'
            workflow_file.write_text(workflow_yaml)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(str(workflow_file))

            state_dir = workspace / '.orchestrate' / 'test_run'
            state_dir.mkdir(parents=True)
            state_manager = StateManager(state_dir)
            state_manager.initialize(str(workflow_file))

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager
            )

            # Execute
            state = executor.execute()

            # First step should execute (no .lock files)
            assert state['steps']['CheckNotExists']['exit_code'] == 0
            assert 'output' in state['steps']['CheckNotExists']

            # Second step should be skipped (file exists)
            assert state['steps']['CheckExists']['status'] == 'skipped'
            assert state['steps']['CheckExists']['exit_code'] == 0
            assert state['steps']['CheckExists'].get('skipped') is True

    def test_condition_with_variables_in_workflow(self):
        """Conditions should support variable substitution in workflows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create workflow with variable-based condition
            workflow_yaml = """
version: "1.1"
name: "Variable Condition Test"
context:
  environment: "production"
steps:
  - name: InitStep
    command: ["echo", "init"]
    output_capture: "text"
  - name: ConditionalStep
    command: ["echo", "In production"]
    when:
      equals:
        left: "${context.environment}"
        right: "production"
  - name: SkipStep
    command: ["echo", "Not in dev"]
    when:
      equals:
        left: "${context.environment}"
        right: "development"
"""
            workflow_file = workspace / 'workflow.yaml'
            workflow_file.write_text(workflow_yaml)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(str(workflow_file))

            state_dir = workspace / '.orchestrate' / 'test_run'
            state_dir.mkdir(parents=True)
            state_manager = StateManager(state_dir)
            state_manager.initialize(str(workflow_file))

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager
            )

            # Execute
            state = executor.execute()

            # Init step always runs
            assert state['steps']['InitStep']['exit_code'] == 0

            # Conditional step should run (env = production)
            assert state['steps']['ConditionalStep']['exit_code'] == 0
            assert 'output' in state['steps']['ConditionalStep']

            # Skip step should be skipped (env != development)
            assert state['steps']['SkipStep']['status'] == 'skipped'
            assert state['steps']['SkipStep']['exit_code'] == 0

    def test_condition_in_for_each_loop(self):
        """Conditions should work within for-each loops."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create workflow with conditional steps in loop
            workflow_yaml = """
version: "1.1"
name: "Loop Condition Test"
steps:
  - name: ProcessItems
    for_each:
      items: ["skip", "process", "skip", "process"]
      steps:
        - name: ConditionalProcess
          command: ["echo", "Processing ${item}"]
          when:
            equals:
              left: "${item}"
              right: "process"
"""
            workflow_file = workspace / 'workflow.yaml'
            workflow_file.write_text(workflow_yaml)

            # Load and execute workflow
            loader = WorkflowLoader(workspace)
            workflow = loader.load(str(workflow_file))

            state_dir = workspace / '.orchestrate' / 'test_run'
            state_dir.mkdir(parents=True)
            state_manager = StateManager(state_dir)
            state_manager.initialize(str(workflow_file))

            executor = WorkflowExecutor(
                workflow=workflow,
                workspace=workspace,
                state_manager=state_manager
            )

            # Execute
            state = executor.execute()

            # Check loop results
            assert 'steps' in state
            assert 'ProcessItems' in state['steps']
            loop_results = state['steps']['ProcessItems']
            assert isinstance(loop_results, list)
            assert len(loop_results) == 4

            # Items 0 and 2 should be skipped (item = "skip")
            assert loop_results[0]['ConditionalProcess']['status'] == 'skipped'
            assert loop_results[2]['ConditionalProcess']['status'] == 'skipped'

            # Items 1 and 3 should execute (item = "process")
            assert loop_results[1]['ConditionalProcess']['exit_code'] == 0
            assert 'output' in loop_results[1]['ConditionalProcess']
            assert loop_results[3]['ConditionalProcess']['exit_code'] == 0
            assert 'output' in loop_results[3]['ConditionalProcess']