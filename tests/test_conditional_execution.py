"""
Test suite for conditional execution (when.equals/exists/not_exists).
Tests AT-37, AT-46, AT-47.
"""

import tempfile
from pathlib import Path
import pytest

from orchestrator.workflow.conditions import ConditionEvaluator


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

    def test_v16_gate_compare_condition_true(self):
        """v1.6 typed gate predicates can compare structured refs to literals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            evaluator = ConditionEvaluator(Path(tmpdir))
            condition = {
                'compare': {
                    'left': {'ref': 'root.steps.Score.artifacts.total'},
                    'op': 'gte',
                    'right': 5,
                }
            }
            state = {
                'steps': {
                    'Score': {
                        'status': 'completed',
                        'exit_code': 0,
                        'artifacts': {'total': 7},
                        'outcome': {
                            'status': 'completed',
                            'phase': 'execution',
                            'class': 'completed',
                            'retryable': False,
                        },
                    }
                }
            }
            assert evaluator.evaluate(condition, {}, state) is True
