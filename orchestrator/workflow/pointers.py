"""
Pointer resolution for step outputs.
Implements AT-3, AT-13: Dynamic for-each with items_from pointer resolution.
"""

import re
from typing import Any, Dict, List, Optional, Union


class PointerResolver:
    """
    Resolves pointers to step outputs following the grammar:
    - steps.<Name>.lines - array of lines from step output
    - steps.<Name>.json[.<dot.path>] - JSON object or nested path
    """

    # Pattern to parse pointer syntax: steps.StepName.field[.nested.path]
    POINTER_PATTERN = re.compile(r'^steps\.([^.]+)\.(.+)$')

    def __init__(self, state: Dict[str, Any]):
        """
        Initialize pointer resolver with execution state.

        Args:
            state: Full orchestration state containing steps results
        """
        self.state = state

    def resolve(self, pointer: str) -> Any:
        """
        Resolve a pointer to its value.

        Args:
            pointer: Pointer string like "steps.List.lines" or "steps.Parse.json.files"

        Returns:
            Resolved value (typically an array for for_each)

        Raises:
            ValueError: If pointer is invalid or doesn't resolve to a value
        """
        match = self.POINTER_PATTERN.match(pointer)
        if not match:
            raise ValueError(f"Invalid pointer syntax: {pointer}")

        step_name = match.group(1)
        field_path = match.group(2)

        # Get step results from state
        steps = self.state.get('steps', {})
        if step_name not in steps:
            raise ValueError(f"Step '{step_name}' not found in state")

        step_data = steps[step_name]

        # Handle array indexing for loop iterations
        # If step_name contains [i], it's a loop iteration reference
        if '[' in step_name:
            # This is handled by the executor for loop-scoped resolution
            raise ValueError(f"Loop iteration references not supported in items_from: {pointer}")

        # Parse the field path
        path_parts = field_path.split('.')
        if not path_parts:
            raise ValueError(f"Invalid field path in pointer: {pointer}")

        # First part must be 'lines' or 'json'
        first = path_parts[0]

        if first == 'lines':
            if len(path_parts) != 1:
                raise ValueError(f"'lines' cannot have nested paths: {pointer}")
            if 'lines' not in step_data:
                raise ValueError(f"Step '{step_name}' does not have 'lines' output")
            return step_data['lines']

        elif first == 'json':
            if 'json' not in step_data:
                raise ValueError(f"Step '{step_name}' does not have 'json' output")

            # Navigate nested JSON path
            result = step_data['json']
            for part in path_parts[1:]:  # Skip 'json' itself
                if not isinstance(result, dict):
                    raise ValueError(f"Cannot navigate path '{field_path}' - '{part}' is not an object")
                if part not in result:
                    raise ValueError(f"Path '{field_path}' not found - missing key '{part}'")
                result = result[part]

            return result

        else:
            raise ValueError(f"Invalid output field '{first}' - must be 'lines' or 'json'")

    def resolve_safe(self, pointer: str) -> tuple[bool, Any, Optional[str]]:
        """
        Safely resolve a pointer, returning success status and error message.

        Args:
            pointer: Pointer string to resolve

        Returns:
            (success, value, error_message) tuple
        """
        try:
            value = self.resolve(pointer)
            return True, value, None
        except ValueError as e:
            return False, None, str(e)