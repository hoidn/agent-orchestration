"""Provider template resolution and command building.

Implements AT-8, AT-9, AT-48, AT-49, AT-50, AT-51 per specs/providers.md.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING

from orchestrator.workflow.types import Step, ProviderTemplate, InputMode

if TYPE_CHECKING:
    from orchestrator.deps import ResolvedDependencies


class ProviderError(Exception):
    """Provider execution error."""
    pass


class TemplateResolver:
    """Resolves provider templates and builds commands."""

    def __init__(
        self,
        providers: Dict[str, ProviderTemplate],
        workspace: Path
    ):
        """Initialize template resolver.

        Args:
            providers: Provider templates from workflow
            workspace: Workspace root directory
        """
        self.providers = providers
        self.workspace = workspace

    def build_provider_command(
        self,
        step: Step,
        context: Dict[str, Any],
        loop_vars: Optional[Dict[str, str]] = None,
        resolved_dependencies: Optional['ResolvedDependencies'] = None
    ) -> Tuple[List[str], Optional[bytes], Dict[str, Any]]:
        """Build command for provider step per specs/providers.md.

        Implements the substitution pipeline:
        1. Compose prompt from input_file (and injection if present)
        2. Merge defaults with provider_params (step wins)
        3. Substitute inside provider_params values
        4. Substitute template tokens: ${PROMPT}, ${<param>}, ${run|context|loop|steps.*}
        5. Apply escapes: $$ → $, $${ → ${
        6. Validate unresolved placeholders

        Args:
            step: Provider step
            context: Variable context with run, context, steps namespaces
            loop_vars: Optional loop variables
            resolved_dependencies: Optional resolved dependencies for injection

        Returns:
            Tuple of (command, stdin_input, error_context)

        Raises:
            ProviderError: On validation failures
        """
        if not step.provider:
            raise ProviderError("Step does not specify a provider")

        if step.provider not in self.providers:
            raise ProviderError(f"Unknown provider: {step.provider}")

        template = self.providers[step.provider]

        # Step 1: Compose prompt from input_file
        prompt, injection_debug = self._compose_prompt(step, context, loop_vars, resolved_dependencies)

        # Step 2: Merge defaults with provider_params (step wins)
        params = dict(template.defaults)
        if step.provider_params:
            params.update(step.provider_params)

        # Step 3: Substitute inside provider_params values (strings only)
        substituted_params = self._substitute_params(params, context, loop_vars)

        # Step 4: Build command with substitutions
        if template.input_mode == InputMode.STDIN:
            # Stdin mode: prompt goes to stdin, no ${PROMPT} allowed
            command = self._substitute_command(
                template.command,
                substituted_params,
                context,
                loop_vars,
                prompt=None  # No ${PROMPT} substitution
            )
            stdin_input = prompt.encode('utf-8') if prompt else None

            # AT-49: Check for invalid ${PROMPT} in stdin mode
            for arg in template.command:
                if '${PROMPT}' in arg:
                    raise ProviderError(
                        f"invalid_prompt_placeholder: ${{{{'PROMPT'}}}} not allowed in stdin mode"
                    )
        else:
            # Argv mode: ${PROMPT} substituted into command
            command = self._substitute_command(
                template.command,
                substituted_params,
                context,
                loop_vars,
                prompt=prompt
            )
            stdin_input = None

        # Step 6: Check for unresolved placeholders
        missing_placeholders = self._find_unresolved_placeholders(command)
        if missing_placeholders:
            error_context = {
                'missing_placeholders': missing_placeholders
            }
            return command, stdin_input, error_context

        # Build error context with injection debug if present
        error_context = {}
        if injection_debug:
            error_context['injection_debug'] = injection_debug

        return command, stdin_input, error_context

    def _compose_prompt(
        self,
        step: Step,
        context: Dict[str, Any],
        loop_vars: Optional[Dict[str, str]] = None,
        resolved_dependencies: Optional['ResolvedDependencies'] = None
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Compose prompt from input file and optional injection.

        Args:
            step: Step with input_file and injection config
            context: Variable context
            loop_vars: Optional loop variables
            resolved_dependencies: Optional resolved dependencies for injection

        Returns:
            Tuple of (prompt, injection_debug_info)
        """
        if not step.input_file:
            return "", None

        input_path = self.workspace / step.input_file
        if not input_path.exists():
            raise ProviderError(f"Input file not found: {step.input_file}")

        try:
            prompt = input_path.read_text()
        except Exception as e:
            raise ProviderError(f"Failed to read input file: {e}")

        # Apply dependency injection if configured
        injection_debug = None
        if step.depends_on and step.depends_on.inject and resolved_dependencies:
            from orchestrator.deps import DependencyInjector

            injector = DependencyInjector(str(self.workspace))
            result = injector.inject(
                prompt,
                resolved_dependencies.all_files,
                step.depends_on.inject
            )

            prompt = result.injected_content

            # Record debug info if truncated
            if result.truncated:
                injection_debug = {
                    "injection_truncated": True,
                    "total_bytes": result.total_bytes,
                    "shown_bytes": result.shown_bytes,
                    "truncated_files": result.truncated_files
                }

        return prompt, injection_debug

    def _substitute_params(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
        loop_vars: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Substitute variables in provider_params values (AT-51).

        Only substitutes string values; recursively visits arrays/objects;
        non-strings unchanged.
        """
        result = {}
        for key, value in params.items():
            if isinstance(value, str):
                # Substitute string values
                result[key] = self._substitute_value(value, context, loop_vars)
            elif isinstance(value, dict):
                # Recursively substitute in nested dicts
                result[key] = self._substitute_params(value, context, loop_vars)
            elif isinstance(value, list):
                # Recursively substitute in lists
                result[key] = [
                    self.substitutor.substitute(item, context, loop_vars)
                    if isinstance(item, str) else item
                    for item in value
                ]
            else:
                # Non-strings unchanged
                result[key] = value
        return result

    def _substitute_command(
        self,
        command: List[str],
        params: Dict[str, Any],
        context: Dict[str, Any],
        loop_vars: Optional[Dict[str, str]] = None,
        prompt: Optional[str] = None
    ) -> List[str]:
        """Substitute placeholders in command template.

        Substitutes:
        - ${PROMPT} with prompt (if prompt is not None)
        - ${<param>} with parameter values
        - ${run|context|loop|steps.*} with context values
        """
        result = []
        for arg in command:
            # First apply escape sequences: $$ -> $, $${ -> ${
            # Temporarily replace $${ to avoid it being treated as ${}
            arg = arg.replace('$${', '\x00ESCAPE_BRACE\x00')
            arg = arg.replace('$$', '\x00ESCAPE_DOLLAR\x00')

            # Then substitute ${PROMPT} if present and allowed
            if prompt is not None:
                arg = arg.replace('${PROMPT}', prompt)

            # Then substitute provider params
            for key, value in params.items():
                placeholder = f'${{{key}}}'
                if placeholder in arg:
                    # Convert value to string for substitution
                    str_value = str(value) if value is not None else ''
                    arg = arg.replace(placeholder, str_value)

            # Then substitute variables from context
            arg = self._substitute_value(arg, context, loop_vars)

            # Finally restore escape sequences
            arg = arg.replace('\x00ESCAPE_BRACE\x00', '${')
            arg = arg.replace('\x00ESCAPE_DOLLAR\x00', '$')

            result.append(arg)
        return result

    def _find_unresolved_placeholders(self, command: List[str]) -> List[str]:
        """Find any unresolved ${...} placeholders in command (AT-48).

        Returns list of placeholder names (bare keys without ${}).
        """
        pattern = re.compile(r'\$\{([^}]+)\}')
        missing = []

        for arg in command:
            for match in pattern.finditer(arg):
                placeholder = match.group(1)
                # Skip escaped placeholders
                if not arg[max(0, match.start()-1):match.start()] == '$':
                    missing.append(placeholder)

        return list(set(missing))  # Deduplicate

    def _substitute_value(
        self,
        value: str,
        context: Dict[str, Any],
        loop_vars: Optional[Dict[str, str]] = None
    ) -> str:
        """Substitute variables in a string value.

        Handles ${run.*}, ${context.*}, ${steps.*}, ${loop.*}, ${item} variables.
        Note: Escape sequences are handled by the caller.
        """

        # Pattern to match ${...} variables
        pattern = re.compile(r'\$\{([^}]+)\}')

        def replacer(match):
            var_path = match.group(1)
            parts = var_path.split('.')

            # Check for env.* namespace (forbidden)
            if parts[0] == 'env':
                raise ProviderError(f"Environment namespace not allowed: ${{{{env.*}}}}")

            # Handle different namespaces
            if parts[0] == 'run' and 'run' in context:
                return self._get_nested_value(context['run'], parts[1:])
            elif parts[0] == 'context' and 'context' in context:
                return self._get_nested_value(context['context'], parts[1:])
            elif parts[0] == 'steps' and 'steps' in context:
                return self._get_nested_value(context['steps'], parts[1:])
            elif parts[0] == 'loop' and loop_vars:
                return loop_vars.get(var_path, match.group(0))
            elif parts[0] == 'item' and loop_vars and 'item' in loop_vars:
                return loop_vars['item']
            else:
                # Leave unresolved for later detection
                return match.group(0)

        # Don't process escape sequences here - already handled in _substitute_command
        return pattern.sub(replacer, value)

    def _get_nested_value(self, obj: Any, path: List[str]) -> str:
        """Get nested value from object using path."""
        for part in path:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                return f"${{{{{'.'}.join([path[0]] + path)}}}}"  # Return unresolved
        return str(obj) if obj is not None else ''