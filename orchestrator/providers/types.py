"""
Provider type definitions for the orchestrator.

Defines data models for provider templates and parameters following specs/providers.md.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Literal, Any
from enum import Enum


class InputMode(str, Enum):
    """Provider input mode for prompt delivery."""
    ARGV = "argv"
    STDIN = "stdin"


@dataclass
class ProviderTemplate:
    """
    Provider template definition.

    Attributes:
        name: Provider identifier (e.g., 'claude', 'gemini')
        command: Command template array with placeholders
        defaults: Default parameter values (supports nested for AT-44)
        input_mode: How to deliver the prompt (argv or stdin)
    """
    name: str
    command: List[str]
    defaults: Dict[str, Any] = field(default_factory=dict)
    input_mode: InputMode = InputMode.ARGV

    def validate(self) -> List[str]:
        """
        Validate provider template configuration.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Command must not be empty
        if not self.command:
            errors.append(f"Provider '{self.name}': command cannot be empty")

        # In stdin mode, ${PROMPT} must not appear in command
        if self.input_mode == InputMode.STDIN:
            for token in self.command:
                if "${PROMPT}" in token:
                    errors.append(
                        f"Provider '{self.name}': ${{PROMPT}} not allowed in stdin mode"
                    )

        return errors


@dataclass
class ProviderParams:
    """
    Parameters for provider invocation.

    Attributes:
        params: Parameter mapping (supports nested structures for AT-44)
        input_file: Optional file containing the prompt
        output_file: Optional file to capture stdout
    """
    params: Dict[str, Any] = field(default_factory=dict)
    input_file: Optional[str] = None
    output_file: Optional[str] = None


@dataclass
class ProviderInvocation:
    """
    Resolved provider invocation ready for execution.

    Attributes:
        command: Fully resolved command array
        input_mode: How to deliver prompt
        prompt: The composed prompt (if any)
        output_file: File to capture stdout (if any)
        env: Additional environment variables
        timeout_sec: Execution timeout
    """
    command: List[str]
    input_mode: InputMode
    prompt: Optional[str] = None
    output_file: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    timeout_sec: Optional[int] = None