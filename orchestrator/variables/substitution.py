"""
Variable substitution implementation.
Handles ${var} resolution with namespaces: run, loop, steps, context.
Per specs/variables.md.
"""

import re
from typing import Any, Dict, List, Optional, Set, Union
from pathlib import Path


class VariableSubstitutor:
    """
    Handles variable substitution in strings and data structures.

    Supports namespaces:
    - run: ${run.id}, ${run.root}, ${run.timestamp_utc}
    - loop: ${item}, ${loop.index}, ${loop.total}
    - steps: ${steps.<name>.exit_code}, ${steps.<name>.output|lines|json}
    - context: ${context.<key>}
    """

    # Pattern to match ${...} variables, handling escaped $$
    VAR_PATTERN = re.compile(r'(?<!\$)\$\{([^}]+)\}')

    def __init__(self):
        """Initialize the substitutor."""
        self.undefined_vars: Set[str] = set()

    def substitute(
        self,
        value: Union[str, List, Dict, Any],
        variables: Dict[str, Any],
        track_undefined: bool = True
    ) -> Union[str, List, Dict, Any]:
        """
        Substitute variables in a value (string, list, or dict).

        Args:
            value: The value to substitute variables in
            variables: Available variables dict with namespaces
            track_undefined: Whether to track undefined variables

        Returns:
            Value with variables substituted

        Raises:
            ValueError: If undefined variables are found (when track_undefined=True)
        """
        self.undefined_vars.clear()

        if isinstance(value, str):
            result = self._substitute_string(value, variables)
            if track_undefined and self.undefined_vars:
                raise ValueError(f"Undefined variables: {sorted(self.undefined_vars)}")
            return result
        elif isinstance(value, list):
            result = [self.substitute(item, variables, track_undefined=False) for item in value]
            if track_undefined and self.undefined_vars:
                raise ValueError(f"Undefined variables: {sorted(self.undefined_vars)}")
            return result
        elif isinstance(value, dict):
            result = {k: self.substitute(v, variables, track_undefined=False) for k, v in value.items()}
            if track_undefined and self.undefined_vars:
                raise ValueError(f"Undefined variables: {sorted(self.undefined_vars)}")
            return result
        else:
            # Non-string/list/dict values pass through unchanged
            return value

    def _substitute_string(self, text: str, variables: Dict[str, Any]) -> str:
        """
        Substitute variables in a string.

        Args:
            text: String containing ${var} references
            variables: Available variables

        Returns:
            String with variables substituted
        """
        # First handle escape sequences: $$ -> $
        text = text.replace('$$', '\x00')  # Use null byte as temporary marker

        def replace_var(match):
            var_path = match.group(1)
            value = self._resolve_variable(var_path, variables)

            if value is None:
                self.undefined_vars.add(var_path)
                # Return original for now, error will be raised later if tracking
                return match.group(0)

            # Convert to string
            if isinstance(value, bool):
                return 'true' if value else 'false'
            elif isinstance(value, (int, float)):
                return str(value)
            elif isinstance(value, str):
                return value
            else:
                # Complex types get JSON representation
                import json
                return json.dumps(value)

        result = self.VAR_PATTERN.sub(replace_var, text)

        # Restore escaped $ from temporary marker
        result = result.replace('\x00', '$')

        return result

    def _resolve_variable(self, var_path: str, variables: Dict[str, Any]) -> Optional[Any]:
        """
        Resolve a variable path like 'context.key' or 'steps.StepName.output'.

        Args:
            var_path: Variable path to resolve
            variables: Available variables

        Returns:
            Resolved value or None if not found
        """
        parts = var_path.split('.')
        if not parts:
            return None

        # Start with the namespace
        namespace = parts[0]

        # Check if this is a simple variable without namespace
        if namespace in variables and len(parts) == 1:
            return variables[namespace]

        # Handle namespaced variables
        if namespace == 'run':
            return self._resolve_path(variables.get('run', {}), parts[1:])
        elif namespace == 'loop':
            return self._resolve_path(variables.get('loop', {}), parts[1:])
        elif namespace == 'context':
            return self._resolve_path(variables.get('context', {}), parts[1:])
        elif namespace == 'steps':
            return self._resolve_steps_variable(variables.get('steps', {}), parts[1:])
        elif namespace == 'item':
            # Special case: ${item} references the loop item directly
            return variables.get('item')
        else:
            # Unknown namespace
            return None

    def _resolve_path(self, obj: Any, path: List[str]) -> Optional[Any]:
        """
        Resolve a path within an object.

        Args:
            obj: Object to traverse
            path: Path parts to follow

        Returns:
            Resolved value or None
        """
        current = obj
        for part in path:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return None
            else:
                return None
        return current

    def _resolve_steps_variable(self, steps: Dict[str, Any], path: List[str]) -> Optional[Any]:
        """
        Resolve a steps.* variable.

        Args:
            steps: Steps results dictionary
            path: Path parts after 'steps'

        Returns:
            Resolved value or None
        """
        if not path:
            return None

        step_name = path[0]
        if step_name not in steps:
            return None

        step_result = steps[step_name]

        if len(path) == 1:
            # Return entire step result
            return step_result

        # Navigate into step result
        return self._resolve_path(step_result, path[1:])

    def build_variables(
        self,
        run_state: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, str]] = None,
        loop_vars: Optional[Dict[str, Any]] = None,
        item: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Build a variables dictionary from various sources.

        Args:
            run_state: Current run state
            context: Context variables
            loop_vars: Loop variables (index, total)
            item: Current loop item

        Returns:
            Combined variables dictionary
        """
        variables = {}

        # Add run variables
        if run_state:
            variables['run'] = {
                'id': run_state.get('run_id', ''),
                'root': run_state.get('run_root', ''),
                'timestamp_utc': run_state.get('started_at', '')
            }

            # Add steps results
            variables['steps'] = run_state.get('steps', {})

        # Add context
        if context:
            variables['context'] = context

        # Add loop variables
        if loop_vars:
            variables['loop'] = loop_vars

        # Add item (for for-each loops)
        if item is not None:
            variables['item'] = item

        return variables