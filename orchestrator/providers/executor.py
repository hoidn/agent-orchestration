"""
Provider executor for running provider commands.

Implements provider execution with argv/stdin modes, placeholder substitution,
and error handling per specs/providers.md.
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

from .types import ProviderTemplate, ProviderInvocation, InputMode, ProviderParams
from .registry import ProviderRegistry


logger = logging.getLogger(__name__)


@dataclass
class ProviderExecutionResult:
    """Result from provider execution."""
    exit_code: int
    stdout: bytes
    stderr: bytes
    duration_ms: int
    error: Optional[Dict[str, Any]] = None
    missing_placeholders: Optional[List[str]] = None
    invalid_prompt_placeholder: bool = False


class ProviderExecutor:
    """
    Executes provider commands with proper input handling.

    Handles argv vs stdin modes, placeholder substitution, and validation
    per specs/providers.md.
    """

    def __init__(self, workspace: Path, registry: ProviderRegistry):
        """
        Initialize provider executor.

        Args:
            workspace: Base workspace directory
            registry: Provider registry for template lookup
        """
        self.workspace = workspace
        self.registry = registry

    def prepare_invocation(
        self,
        provider_name: str,
        params: ProviderParams,
        context: Dict[str, str],
        prompt_content: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_sec: Optional[int] = None,
    ) -> Tuple[Optional[ProviderInvocation], Optional[Dict[str, Any]]]:
        """
        Prepare a provider invocation.

        Args:
            provider_name: Name of the provider to invoke
            params: Provider parameters
            context: Variable context for substitution
            prompt_content: Composed prompt content (from input_file + injection)
            env: Additional environment variables
            timeout_sec: Execution timeout

        Returns:
            Tuple of (invocation, error_dict) - error_dict is None if successful
        """
        # Get provider template
        provider = self.registry.get(provider_name)
        if not provider:
            return None, {
                "type": "provider_not_found",
                "message": f"Provider '{provider_name}' not found",
                "context": {"provider": provider_name}
            }

        # Merge parameters (step params override defaults)
        merged_params = self.registry.merge_params(provider_name, params.params)

        # Substitute variables in provider_params values (AT-51)
        substituted_params, param_errors = self._substitute_params(merged_params, context)
        if param_errors:
            return None, {
                "type": "substitution_error",
                "message": "Failed to substitute provider parameters",
                "context": {"errors": param_errors}
            }

        # Build command with substitution
        command, missing_placeholders, invalid_prompt = self._build_command(
            provider,
            substituted_params,
            context,
            prompt_content
        )

        # Check for validation errors
        if invalid_prompt:
            return None, {
                "type": "validation_error",
                "message": "Invalid ${PROMPT} placeholder in stdin mode",
                "context": {"invalid_prompt_placeholder": True}
            }

        if missing_placeholders:
            return None, {
                "type": "validation_error",
                "message": f"Missing placeholders: {', '.join(missing_placeholders)}",
                "context": {"missing_placeholders": missing_placeholders}
            }

        invocation = ProviderInvocation(
            command=command,
            input_mode=provider.input_mode,
            prompt=prompt_content if provider.input_mode == InputMode.STDIN else None,
            output_file=params.output_file,
            env=env or {},
            timeout_sec=timeout_sec
        )

        return invocation, None

    def execute(
        self,
        invocation: ProviderInvocation,
        cwd: Optional[Path] = None
    ) -> ProviderExecutionResult:
        """
        Execute a prepared provider invocation.

        Args:
            invocation: Provider invocation to execute
            cwd: Working directory (default: workspace)

        Returns:
            Execution result with output and metadata
        """
        working_dir = cwd or self.workspace
        start_time = time.time()

        # Setup environment
        import os
        process_env = os.environ.copy()
        if invocation.env:
            process_env.update(invocation.env)

        try:
            # Prepare stdin if needed
            stdin_input = None
            stdin_pipe = None
            if invocation.input_mode == InputMode.STDIN and invocation.prompt:
                stdin_input = invocation.prompt.encode('utf-8')
                stdin_pipe = subprocess.PIPE

            logger.debug(f"Executing command: {invocation.command}")
            if invocation.input_mode == InputMode.STDIN:
                logger.debug(f"Using stdin mode, prompt size: {len(invocation.prompt or '')} bytes")

            # Execute command
            result = subprocess.run(
                invocation.command,
                cwd=str(working_dir),
                env=process_env,
                stdin=stdin_pipe,
                input=stdin_input,
                capture_output=True,
                timeout=invocation.timeout_sec,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            return ProviderExecutionResult(
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms
            )

        except subprocess.TimeoutExpired as e:
            # Timeout: exit code 124 per spec
            duration_ms = int((time.time() - start_time) * 1000)
            return ProviderExecutionResult(
                exit_code=124,
                stdout=e.stdout or b"",
                stderr=e.stderr or b"",
                duration_ms=duration_ms,
                error={
                    "type": "timeout",
                    "message": f"Provider timed out after {invocation.timeout_sec} seconds",
                    "context": {"timeout_sec": invocation.timeout_sec}
                }
            )

        except Exception as e:
            # Other execution errors
            duration_ms = int((time.time() - start_time) * 1000)
            return ProviderExecutionResult(
                exit_code=1,
                stdout=b"",
                stderr=str(e).encode('utf-8'),
                duration_ms=duration_ms,
                error={
                    "type": "execution_error",
                    "message": str(e),
                    "context": {}
                }
            )

    def _substitute_params(
        self,
        params: Dict[str, str],
        context: Dict[str, str]
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Substitute variables in provider parameters.

        Args:
            params: Provider parameters
            context: Variable context

        Returns:
            Tuple of (substituted_params, errors)
        """
        import re

        substituted = {}
        errors = []
        var_pattern = re.compile(r'\$\{([^}]+)\}')

        for key, value in params.items():
            if not isinstance(value, str):
                substituted[key] = value
                continue

            # Apply escapes first
            processed = value.replace('$$', '\x00')  # Temp marker for literal $
            processed = processed.replace('$${', '\x01{')  # Temp marker for literal ${

            # Find all variables
            matches = var_pattern.findall(processed)
            for var in matches:
                if var in context:
                    processed = processed.replace(f"${{{var}}}", context[var])
                else:
                    errors.append(f"Undefined variable in provider_params: ${{{var}}}")

            # Restore escaped literals
            processed = processed.replace('\x00', '$')
            processed = processed.replace('\x01{', '${')

            substituted[key] = processed

        return substituted, errors

    def _build_command(
        self,
        provider: ProviderTemplate,
        params: Dict[str, str],
        context: Dict[str, str],
        prompt: Optional[str]
    ) -> Tuple[List[str], List[str], bool]:
        """
        Build command with placeholder substitution.

        Args:
            provider: Provider template
            params: Merged and substituted parameters
            context: Variable context
            prompt: Composed prompt content

        Returns:
            Tuple of (command, missing_placeholders, invalid_prompt_placeholder)
        """
        import re

        command = []
        missing = set()
        invalid_prompt = False
        var_pattern = re.compile(r'\$\{([^}]+)\}')

        for token in provider.command:
            # Apply escapes first
            processed = token.replace('$$', '\x00')  # Temp marker for literal $
            processed = processed.replace('$${', '\x01{')  # Temp marker for literal ${

            # Handle ${PROMPT} specially
            if "${PROMPT}" in processed:
                if provider.input_mode == InputMode.STDIN:
                    # AT-49: ${PROMPT} not allowed in stdin mode
                    invalid_prompt = True
                    logger.error(f"Provider '{provider.name}': ${{PROMPT}} not allowed in stdin mode")
                elif prompt:
                    processed = processed.replace("${PROMPT}", prompt)
                # If no prompt in argv mode, that's allowed (AT-50)

            # Substitute other placeholders
            for match in var_pattern.finditer(processed):
                var = match.group(1)
                if var == "PROMPT":
                    continue  # Already handled

                # Check provider params first
                if var in params:
                    processed = processed.replace(f"${{{var}}}", params[var])
                # Then check context (run/context/loop/steps.*)
                elif var in context:
                    processed = processed.replace(f"${{{var}}}", context[var])
                else:
                    # AT-48: Missing placeholder
                    missing.add(var)

            # Restore escaped literals
            processed = processed.replace('\x00', '$')
            processed = processed.replace('\x01{', '${')

            command.append(processed)

        return command, list(missing), invalid_prompt