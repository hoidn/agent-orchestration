"""
Condition evaluation for workflow steps.
Implements AT-37, AT-46, AT-47: Conditional execution with when.equals/exists/not_exists.
"""

import glob
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..variables.substitution import VariableSubstitutor


class ConditionEvaluator:
    """
    Evaluates step conditions to determine if a step should be executed.

    Supports:
    - when.equals: String comparison of two values
    - when.exists: Check if files matching glob pattern exist
    - when.not_exists: Check if no files match glob pattern
    """

    def __init__(self, workspace: Path):
        """
        Initialize the condition evaluator.

        Args:
            workspace: Base workspace directory for file existence checks
        """
        self.workspace = Path(workspace).resolve()
        self.substitutor = VariableSubstitutor()

    def evaluate(
        self,
        condition: Optional[Dict[str, Any]],
        variables: Dict[str, Any]
    ) -> bool:
        """
        Evaluate a step condition.

        Args:
            condition: The when condition from the step (None means always true)
            variables: Available variables for substitution

        Returns:
            True if the condition is met (step should execute),
            False if not met (step should be skipped)

        Raises:
            ValueError: If the condition format is invalid
        """
        if condition is None:
            # No condition means always execute
            return True

        if not isinstance(condition, dict):
            raise ValueError(f"Invalid condition format: expected dict, got {type(condition)}")

        # Check for exactly one condition type
        condition_types = ['equals', 'exists', 'not_exists']
        present_types = [k for k in condition_types if k in condition]

        if len(present_types) == 0:
            # No recognized condition type
            raise ValueError(f"No valid condition type found. Expected one of: {condition_types}")
        elif len(present_types) > 1:
            # Multiple condition types (not allowed)
            raise ValueError(f"Multiple condition types found: {present_types}. Only one allowed.")

        # Evaluate the specific condition type
        if 'equals' in condition:
            return self._evaluate_equals(condition['equals'], variables)
        elif 'exists' in condition:
            return self._evaluate_exists(condition['exists'], variables)
        elif 'not_exists' in condition:
            return self._evaluate_not_exists(condition['not_exists'], variables)

        return True

    def _evaluate_equals(self, equals_cond: Dict[str, Any], variables: Dict[str, Any]) -> bool:
        """
        Evaluate a when.equals condition.

        Args:
            equals_cond: Dict with 'left' and 'right' keys
            variables: Available variables

        Returns:
            True if left equals right (as strings)
        """
        if not isinstance(equals_cond, dict):
            raise ValueError(f"Invalid equals condition: expected dict, got {type(equals_cond)}")

        if 'left' not in equals_cond or 'right' not in equals_cond:
            raise ValueError("equals condition must have 'left' and 'right' keys")

        # Substitute variables in both sides
        try:
            left = self.substitutor.substitute(equals_cond['left'], variables)
            right = self.substitutor.substitute(equals_cond['right'], variables)
        except ValueError as e:
            # Undefined variables make the condition false
            # This is a runtime condition evaluation, not a validation error
            return False

        # Convert both to strings for comparison
        left_str = self._to_string(left)
        right_str = self._to_string(right)

        return left_str == right_str

    def _evaluate_exists(self, pattern: str, variables: Dict[str, Any]) -> bool:
        """
        Evaluate a when.exists condition.

        Args:
            pattern: POSIX glob pattern
            variables: Available variables

        Returns:
            True if at least one file matches the pattern
        """
        if not isinstance(pattern, str):
            raise ValueError(f"Invalid exists pattern: expected string, got {type(pattern)}")

        # Substitute variables in the pattern
        try:
            substituted_pattern = self.substitutor.substitute(pattern, variables)
            # Ensure the result is a string (since we passed in a string)
            if not isinstance(substituted_pattern, str):
                raise ValueError(f"Pattern substitution returned unexpected type: {type(substituted_pattern)}")
            pattern = substituted_pattern
        except ValueError:
            # Undefined variables make the condition false
            return False

        # Validate path safety
        if not self._is_path_safe(pattern):
            raise ValueError(f"Unsafe path in exists condition: {pattern}")

        # Resolve pattern relative to workspace
        full_pattern = self.workspace / pattern

        # Use glob to find matches
        matches = glob.glob(str(full_pattern))

        # Follow symlinks and verify they stay within workspace
        for match_path in matches:
            resolved = Path(match_path).resolve()
            try:
                resolved.relative_to(self.workspace)
            except ValueError:
                # Symlink escapes workspace, don't count it
                continue
            # At least one valid match found
            return True

        return False

    def _evaluate_not_exists(self, pattern: str, variables: Dict[str, Any]) -> bool:
        """
        Evaluate a when.not_exists condition.

        Args:
            pattern: POSIX glob pattern
            variables: Available variables

        Returns:
            True if no files match the pattern
        """
        # not_exists is just the inverse of exists
        return not self._evaluate_exists(pattern, variables)

    def _to_string(self, value: Any) -> str:
        """
        Convert a value to string for comparison.

        Args:
            value: Value to convert

        Returns:
            String representation
        """
        if isinstance(value, bool):
            return 'true' if value else 'false'
        elif isinstance(value, str):
            return value
        else:
            return str(value)

    def _is_path_safe(self, path: str) -> bool:
        """
        Check if a path is safe (no absolute paths or parent traversal).

        Args:
            path: Path to check

        Returns:
            True if safe, False otherwise
        """
        # Check for absolute paths
        if Path(path).is_absolute():
            return False

        # Check for parent traversal
        if '..' in Path(path).parts:
            return False

        return True