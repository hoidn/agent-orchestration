"""Variable substitution for DSL values per specs/variables.md"""

import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class SubstitutionContext:
    """Context for variable substitution"""
    run: Dict[str, Any]  # run.id, run.root, run.timestamp_utc
    context: Dict[str, str]  # context.<key> from workflow
    steps: Dict[str, Dict[str, Any]]  # steps.<name>.* results
    loop: Optional[Dict[str, Any]] = None  # item, loop.index, loop.total for for_each
    item: Optional[Any] = None  # current item in for_each loop


class VariableSubstitutor:
    """Handles variable substitution in workflow values"""

    # Pattern to match ${...} variables (but not escaped $${...})
    VAR_PATTERN = re.compile(r'(?<!\$)\$\{([^}]+)\}')

    def __init__(self, context: SubstitutionContext):
        """Initialize with substitution context"""
        self.context = context

    def substitute(self, value: Any) -> Any:
        """
        Substitute variables in a value.

        Args:
            value: Value to process (string, list, dict, or other)

        Returns:
            Value with variables substituted

        Raises:
            ValueError: If undefined variable or env.* namespace used
        """
        if isinstance(value, str):
            return self._substitute_string(value)
        elif isinstance(value, list):
            return [self.substitute(item) for item in value]
        elif isinstance(value, dict):
            return {k: self.substitute(v) for k, v in value.items()}
        else:
            # Numbers, booleans, None pass through unchanged
            return value

    def _substitute_string(self, text: str) -> str:
        """
        Substitute variables in a string.

        Handles:
        - ${run.*}, ${context.*}, ${steps.*}, ${loop.*}, ${item}
        - Escapes: $$ -> $, $${ -> ${
        - Rejects ${env.*} namespace
        """
        # First handle escapes: $$ -> $ and $${ -> ${
        text = text.replace('$${', '\x00ESCAPED_DOLLAR_BRACE\x00')
        text = text.replace('$$', '\x00ESCAPED_DOLLAR\x00')

        # Find all variables
        def replacer(match):
            var_path = match.group(1)

            # Check for forbidden env.* namespace
            if var_path.startswith('env.'):
                raise ValueError(f"Environment namespace not allowed: ${{env.*}} - found ${{{var_path}}}")

            # Resolve the variable
            value = self._resolve_variable(var_path)

            # Convert to string for substitution
            if value is None:
                raise ValueError(f"Undefined variable: ${{{var_path}}}")

            # Coerce to string (for numbers, booleans, etc.)
            return str(value)

        # Replace all variables
        result = self.VAR_PATTERN.sub(replacer, text)

        # Restore escaped sequences
        result = result.replace('\x00ESCAPED_DOLLAR_BRACE\x00', '${')
        result = result.replace('\x00ESCAPED_DOLLAR\x00', '$')

        return result

    def _resolve_variable(self, path: str) -> Any:
        """
        Resolve a variable path to its value.

        Args:
            path: Variable path like "run.id" or "steps.Build.exit_code"

        Returns:
            Resolved value or None if not found
        """
        parts = path.split('.', 1)
        namespace = parts[0]

        if namespace == 'run':
            if len(parts) < 2:
                return None
            return self.context.run.get(parts[1])

        elif namespace == 'context':
            if len(parts) < 2:
                return None
            return self.context.context.get(parts[1])

        elif namespace == 'item' and self.context.item is not None:
            # ${item} in for_each loop
            return self.context.item

        elif namespace == 'loop' and self.context.loop is not None:
            if len(parts) < 2:
                return None
            return self.context.loop.get(parts[1])

        elif namespace == 'steps':
            if len(parts) < 2:
                return None
            # Parse steps.<name>.field or steps.<name>.json.path
            step_parts = parts[1].split('.', 1)
            step_name = step_parts[0]

            if step_name not in self.context.steps:
                return None

            step_data = self.context.steps[step_name]

            if len(step_parts) == 1:
                # Just steps.<name> - return the whole step data?
                return None  # Not a valid reference

            # Navigate the path within the step
            field_path = step_parts[1]
            return self._navigate_path(step_data, field_path)

        return None

    def _navigate_path(self, data: Any, path: str) -> Any:
        """
        Navigate a dot-separated path in nested data.

        Args:
            data: Data structure to navigate
            path: Dot-separated path like "json.files" or "exit_code"

        Returns:
            Value at path or None if not found
        """
        parts = path.split('.')
        current = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return None
            else:
                return None

        return current


def substitute_value(value: Any, context: SubstitutionContext) -> Any:
    """
    Convenience function to substitute variables in a value.

    Args:
        value: Value to process
        context: Substitution context

    Returns:
        Value with variables substituted
    """
    substitutor = VariableSubstitutor(context)
    return substitutor.substitute(value)